"""Re-audited offline OCR review timeline; never reconstructs hands or authorizes math.

This is an evidence-only bridge between human OCR annotations and future
manual hand-history reconstruction. Nominal sampling timestamps are NOT source
PTS. Every invocation rechecks the original job, video and frame evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from offline_job_review_decisions import validate_submission, handoff_sha256
from offline_job_review_handoff import build_handoff
from offline_jobs import OfflineJobStore

MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_HINTS = 20_000
FRAME_PATH = re.compile(r'^table_0[1-4]/frame_[0-9]{5}\.png$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
REVIEW_FIELDS = ('table_id', 'nominal_timestamp_seconds', 'field',
                 'candidate_index', 'status', 'value', 'confidence', 'reason')


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def load_report(path):
    """Bounded read of a regular file, refusing final-component symlinks."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_REPORT_BYTES:
            raise ValueError('Invalid report file or size')
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Report exceeds size limit')
    try:
        report = json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicates,
                            parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON report') from exc
    return report, hashlib.sha256(raw).hexdigest()


def verify_saved_review(handoff, saved):
    """Reconstruct the exact report using the *freshly audited* handoff.

    This verifies structural integrity and provenance, NOT human identity or
    whether the reviewer correctly interpreted an image.
    """
    if type(saved) is not dict or type(saved.get('decisions')) is not list:
        raise ValueError('Expected saved human OCR review report')
    decisions = []
    for row in saved['decisions']:
        if type(row) is not dict or set(row) != set(REVIEW_FIELDS) | {'original_ocr_text_unverified'}:
            raise ValueError('Unexpected saved review decision structure')
        decisions.append({key: row[key] for key in REVIEW_FIELDS})
    submission = {
        'schema_version': saved.get('schema_version'),
        'job_id': saved.get('job_id'),
        'handoff_sha256': saved.get('handoff_sha256'),
        'reviewer': saved.get('reviewer'),
        'decisions': decisions,
    }
    canonical = validate_submission(handoff, submission)
    if _json(canonical) != _json(saved):
        raise ValueError('Saved review report differs from revalidated result')
    return canonical


def build_timeline(handoff, saved, report_sha256):
    """Build a non-authoritative chronological index of reviewed OCR *hints*."""
    if type(report_sha256) is not str or not SHA256.fullmatch(report_sha256):
        raise ValueError('Invalid report SHA-256')
    canonical = verify_saved_review(handoff, saved)
    if handoff.get('timestamp_semantics') != 'nominal_sampling_grid_not_exact_source_pts':
        raise ValueError('Unexpected timestamp semantics')
    if handoff.get('hand_reconstruction_verified') is not False or handoff.get('automatic_clip_selection_authorized') is not False:
        raise ValueError('Handoff incorrectly authorizes interpretation')
    if type(handoff.get('ocr_hint_count')) is not int:
        raise ValueError('Invalid OCR hint count')
    by_key = {(row['table_id'], row['nominal_timestamp_seconds'],
               row['field'], row['candidate_index']): row
              for row in canonical['decisions']}
    observations = []
    for frame in handoff['frames']:
        image, digest = frame.get('image'), frame.get('sha256')
        if (type(image) is not str or not FRAME_PATH.fullmatch(image) or
                type(digest) is not str or not SHA256.fullmatch(digest)):
            raise ValueError('Invalid audited image reference')
        table, stamp = frame['table_id'], frame['nominal_timestamp_seconds']
        if type(table) is not int or table not in (1, 2, 3, 4) or type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise ValueError('Invalid audited frame metadata')
        for hint in frame['ocr_hints_unverified']:
            key = (table, float(stamp), hint['field'], hint['candidate_index'])
            decision = by_key.get(key)
            status = decision['status'] if decision else 'pending'
            observations.append({
                'table_id': table, 'nominal_timestamp_seconds': float(stamp),
                'source_image': image, 'source_image_sha256': digest,
                'field': hint['field'], 'candidate_index': hint['candidate_index'],
                'original_ocr_text_unverified': hint['unverified_text'],
                'review_status': status,
                'human_annotation_value': (decision['value'] if status in ('confirmed', 'corrected') else None),
                'human_confidence_subjective': (decision['confidence'] if status in ('confirmed', 'corrected') else None),
                'review_reason': decision['reason'] if decision else None,
                'reviewer': canonical['reviewer'] if decision else None,
                'hand_reconstruction_verified': False,
                'ready_for_equity_or_ev': False,
            })
            if len(observations) > MAX_HINTS:
                raise ValueError('Too many OCR hints for timeline')
    if len(observations) != handoff['ocr_hint_count'] or len(observations) != canonical['reviewed_count'] + canonical['unreviewed_count']:
        raise ValueError('OCR hint count mismatch')
    observations.sort(key=lambda x: (x['table_id'], x['nominal_timestamp_seconds'],
                                     x['candidate_index'], x['field']))
    return {
        'schema_version': 1,
        'analysis_status': 'human_reviewed_ocr_timeline_unverified_no_math',
        'job_id': handoff['job_id'], 'source_sha256': handoff['source_sha256'],
        'source_handoff_sha256': handoff_sha256(handoff),
        'source_review_report_sha256': report_sha256,
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'manifest_frame_hashes_matched': handoff.get('manifest_frame_hashes_matched') is True,
        'audited_frame_count': handoff['frame_count'],
        'observations': observations,
        'counts': {
            'ocr_hints': len(observations), 'reviewed': canonical['reviewed_count'],
            'pending': canonical['unreviewed_count'],
            **canonical['status_counts'],
        },
        'requires_manual_hand_reconstruction': True,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'OCR review is not complete hand reconstruction or proof of card/action correctness.',
            'Nominal frame sampling timestamps are not independently verified source PTS.',
            'Human review confidence is subjective, not a calibrated recognition probability.',
            'Do not calculate equity/EV or automatically select MP4 clips from this timeline.',
        ],
    }


def timeline_job(store, job_id, results_root):
    """Re-audit the current job and saved human report before producing a timeline."""
    if type(job_id) is not str or not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise ValueError('Invalid job ID')
    path = Path(results_root) / job_id / 'human_ocr_review.json'
    saved, digest = load_report(path)
    handoff = build_handoff(store, job_id, results_root)
    timeline = build_timeline(handoff, saved, digest)
    _, final_digest = load_report(path)
    if final_digest != digest:
        raise ValueError('Human review changed during re-audit')
    return timeline


def export_timeline(store, job_id, results_root):
    """Write a single new JSON file without overwriting existing artifacts."""
    result = timeline_job(store, job_id, results_root)
    target = Path(results_root) / job_id / 'human_ocr_timeline.json'
    data = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('job_id')
    parser.add_argument('results_root')
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(argv)
    store = OfflineJobStore(args.database)
    timeline = (export_timeline if args.export else timeline_job)(
        store, args.job_id, args.results_root)
    print(json.dumps({'job_id': timeline['job_id'], 'counts': timeline['counts'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
