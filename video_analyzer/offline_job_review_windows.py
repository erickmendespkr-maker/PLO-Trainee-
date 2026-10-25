"""Conservative OCR observation windows for offline PLO5/PLO6 video review.

A window is a navigation aid, NEVER a reconstructed hand or a mathematical
scenario. Sampling timestamps are nominal and may differ from video PTS.
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

from offline_job_review_timeline import timeline_job

MAX_OBSERVATIONS = 20_000
MAX_WINDOWS = 20_000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
STAMP_LIMIT_SECONDS = 86_400
IMAGE_PATH = re.compile(r'table_0[1-4]/frame_[0-9]{5}\.png\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
JOB_ID = re.compile(r'[0-9a-f]{32}\Z')
STATUSES = {'confirmed', 'corrected', 'uncertain', 'rejected', 'pending'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def build_windows(timeline, *, gap_seconds=15, max_span_seconds=120):
    """Group nearby *observations*, without guessing hand start/end.

    Accepts only a freshly generated timeline when used via windows_job().
    Direct calls are suitable for deterministic tests, not source auditing.
    """
    _require(type(gap_seconds) in (int, float) and math.isfinite(gap_seconds)
             and 0 < gap_seconds <= 120, 'Invalid gap_seconds')
    _require(type(max_span_seconds) in (int, float) and math.isfinite(max_span_seconds)
             and gap_seconds <= max_span_seconds <= 600, 'Invalid max_span_seconds')
    _require(type(timeline) is dict and timeline.get('schema_version') == 1
             and timeline.get('analysis_status') == 'human_reviewed_ocr_timeline_unverified_no_math',
             'Unsupported timeline')
    for flag in ('ready_for_equity_or_ev', 'hand_reconstruction_verified',
                 'automatic_clip_selection_authorized'):
        _require(timeline.get(flag) is False, 'Timeline authorizes prohibited operation')
    _require(timeline.get('timestamp_semantics') == 'nominal_sampling_grid_not_exact_source_pts',
             'Unexpected timestamp semantics')
    _require(timeline.get('requires_manual_hand_reconstruction') is True,
             'Missing manual reconstruction gate')
    job_id = timeline.get('job_id')
    source_sha = timeline.get('source_sha256')
    _require(type(job_id) is str and JOB_ID.fullmatch(job_id) is not None, 'Invalid job ID')
    _require(type(source_sha) is str and HEX.fullmatch(source_sha) is not None, 'Invalid source digest')
    observations = timeline.get('observations')
    _require(type(observations) is list and len(observations) <= MAX_OBSERVATIONS,
             'Invalid observation count')
    counts = timeline.get('counts')
    _require(type(counts) is dict and type(counts.get('ocr_hints')) is int
             and counts['ocr_hints'] == len(observations), 'Timeline count mismatch')
    by_table = {table: [] for table in range(1, 5)}
    seen = set()
    for obs in observations:
        _require(type(obs) is dict, 'Invalid observation')
        table = obs.get('table_id')
        stamp = obs.get('nominal_timestamp_seconds')
        field = obs.get('field')
        candidate = obs.get('candidate_index')
        image = obs.get('source_image')
        digest = obs.get('source_image_sha256')
        status = obs.get('review_status')
        _require(type(table) is int and table in by_table, 'Invalid table')
        _require(type(stamp) in (int, float) and math.isfinite(stamp)
                 and 0 <= stamp <= STAMP_LIMIT_SECONDS, 'Invalid timestamp')
        _require(type(field) is str and 0 < len(field) <= 80, 'Invalid OCR field')
        _require(type(candidate) is int and 0 <= candidate <= MAX_OBSERVATIONS,
                 'Invalid candidate index')
        _require(type(image) is str and IMAGE_PATH.fullmatch(image) is not None
                 and image.startswith(f'table_0{table}/'), 'Invalid image reference')
        _require(type(digest) is str and HEX.fullmatch(digest) is not None, 'Invalid image digest')
        _require(type(status) is str and status in STATUSES, 'Invalid review status')
        approved = status in ('confirmed', 'corrected')
        value = obs.get('human_annotation_value')
        confidence = obs.get('human_confidence_subjective')
        _require((type(value) is str and len(value) <= 1000 and
                  type(confidence) in (int, float) and math.isfinite(confidence) and
                  0 <= confidence <= 1) if approved else
                 (value is None and confidence is None), 'Invalid human annotation')
        _require(obs.get('hand_reconstruction_verified') is False and
                 obs.get('ready_for_equity_or_ev') is False, 'Observation authorizes math')
        key = (table, float(stamp), field, candidate)
        _require(key not in seen, 'Duplicate OCR observation')
        seen.add(key)
        by_table[table].append(obs)

    windows = []
    for table, rows in by_table.items():
        rows.sort(key=lambda r: (r['nominal_timestamp_seconds'], r['candidate_index'], r['field']))
        group = []
        table_window_index = 0
        def flush():
            nonlocal table_window_index
            if not group:
                return
            table_window_index += 1
            stamps = [float(r['nominal_timestamp_seconds']) for r in group]
            status_counts = {s: sum(r['review_status'] == s for r in group) for s in sorted(STATUSES)}
            windows.append({
                'window_id': f'table_{table:02d}_window_{table_window_index:05d}',
                'table_id': table,
                'first_nominal_timestamp_seconds': stamps[0],
                'last_nominal_timestamp_seconds': stamps[-1],
                'observation_count': len(group),
                'source_images': sorted(set(r['source_image'] for r in group)),
                'status_counts': status_counts,
                'has_unresolved_observations': bool(status_counts['pending'] or status_counts['uncertain'] or status_counts['rejected']),
                'observation_keys': [
                    {'nominal_timestamp_seconds': float(r['nominal_timestamp_seconds']),
                     'field': r['field'], 'candidate_index': r['candidate_index'],
                     'source_image_sha256': r['source_image_sha256']}
                    for r in group],
                'provisional_navigation_only': True,
                'hand_start_or_end_verified': False,
                'ready_for_equity_or_ev': False,
            })
        for row in rows:
            stamp = float(row['nominal_timestamp_seconds'])
            if group and (stamp - float(group[-1]['nominal_timestamp_seconds']) > gap_seconds or
                          stamp - float(group[0]['nominal_timestamp_seconds']) > max_span_seconds):
                flush()
                group = []
            group.append(row)
        flush()
    _require(len(windows) <= MAX_WINDOWS, 'Too many windows')
    return {
        'schema_version': 1,
        'analysis_status': 'provisional_ocr_review_windows_not_hands',
        'job_id': job_id,
        'source_sha256': source_sha,
        'source_timeline_sha256': hashlib.sha256(_canonical(timeline)).hexdigest(),
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'gap_seconds': gap_seconds,
        'max_span_seconds': max_span_seconds,
        'observation_count': len(observations),
        'window_count': len(windows),
        'windows': windows,
        'requires_manual_hand_reconstruction': True,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Windows are temporal navigation aids, not identified poker hands.',
            'Nominal sampling timestamps are not verified source presentation timestamps.',
            'OCR annotations are not complete action histories or validated cards.',
            'No equity, EV, automatic clip selection, or strategic error claims are authorized.',
        ],
    }


def windows_job(store, job_id, results_root, *, gap_seconds=15, max_span_seconds=120):
    _require(type(job_id) is str and JOB_ID.fullmatch(job_id) is not None, 'Invalid job ID')
    timeline = timeline_job(store, job_id, results_root)  # re-audits source and human review
    return build_windows(timeline, gap_seconds=gap_seconds, max_span_seconds=max_span_seconds)


def export_windows(store, job_id, results_root, *, gap_seconds=15, max_span_seconds=120):
    result = windows_job(store, job_id, results_root,
                         gap_seconds=gap_seconds, max_span_seconds=max_span_seconds)
    folder = Path(results_root) / job_id
    _require(not folder.is_symlink() and folder.is_dir(), 'Unsafe output directory')
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
    _require(len(payload) <= MAX_OUTPUT_BYTES, 'Output exceeds size limit')
    target = folder / 'human_ocr_review_windows.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output file')
            stream.write(payload)
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
    parser.add_argument('--gap-seconds', type=float, default=15)
    parser.add_argument('--max-span-seconds', type=float, default=120)
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(argv)
    from offline_jobs import OfflineJobStore
    store = OfflineJobStore(args.database)
    fn = export_windows if args.export else windows_job
    report = fn(store, args.job_id, args.results_root,
                gap_seconds=args.gap_seconds, max_span_seconds=args.max_span_seconds)
    print(json.dumps({'job_id': report['job_id'], 'window_count': report['window_count'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
