"""Offline, human-reviewed activity OCR -> provenance-linked decision review queue.

This module does not recognize poker actions or authorize equity/EV. It checks
internal consistency of an *already reviewed* report, optionally pins its
canonical SHA-256, and attaches source-frame references to strictly earlier
observation hints. Original image bytes must still be re-audited upstream.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from decision_snapshot import build_decision_snapshots
from hand_history import Observation

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_OCR_FIELDS = {'pot': 'pot', 'bet': 'amount', 'board': 'board', 'hero_cards': 'hero_cards'}


def canonical_sha256(value):
    """Stable digest of the complete JSON report (not an image-byte audit)."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _same_value(a, b):
    if isinstance(a, (tuple, list)) or isinstance(b, (tuple, list)):
        return isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and list(a) == list(b)
    return type(a) is not bool and type(b) is not bool and a == b


def _source_image(path):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('Invalid source image path')
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or '..' in parsed.parts or path.startswith('./'):
        raise ValueError('Unsafe source image path')
    return path


def build_activity_snapshot_queue(reviewed, *, expected_review_sha256=None,
                                  min_confidence=.75, max_age_seconds=30.):
    """Bind unverified decision hints to human-reviewed, frame-indexed evidence.

    Rejects edits to values, timestamps, table/hand assignments and field
    provenance. It cannot verify that human labels are correct or that the
    upstream image/recording bytes still exist; no EV scenario is produced.
    """
    if not isinstance(reviewed, dict) or reviewed.get('schema_version') != 1:
        raise ValueError('Expected reviewed activity schema version 1')
    if (reviewed.get('analysis_status') != 'human_reviewed_activity_observations'
            or reviewed.get('ready_for_equity_or_ev') is not False):
        raise ValueError('Only human-reviewed, EV-blocked activity reports are allowed')
    for name in ('recording_sha256', 'evidence_manifest_sha256', 'ocr_report_sha256'):
        if not isinstance(reviewed.get(name), str) or not _SHA.fullmatch(reviewed[name]):
            raise ValueError(f'Invalid {name}')
    semantics = reviewed.get('timestamp_semantics')
    if not isinstance(semantics, str) or not semantics or 'decoded' not in semantics.lower():
        raise ValueError('Decoded PTS semantics are required')
    digest = canonical_sha256(reviewed)
    if expected_review_sha256 is not None:
        if (not isinstance(expected_review_sha256, str) or not _SHA.fullmatch(expected_review_sha256)
                or digest != expected_review_sha256):
            raise ValueError('Reviewed report SHA-256 mismatch')
    rows, sources = reviewed.get('observations'), reviewed.get('provenance')
    if (not isinstance(rows, list) or not isinstance(sources, list)
            or len(rows) != len(sources) or len(rows) > 10000):
        raise ValueError('Observations/provenance must align and be bounded')
    observations = []
    provenance_by_index = {}
    seen_candidates = set()
    for index, (row, source) in enumerate(zip(rows, sources)):
        if not isinstance(row, dict) or not isinstance(source, dict):
            raise ValueError('Malformed reviewed observation/provenance')
        obs = Observation(**row)
        if (type(source.get('event_index')) is not int or source['event_index'] != index
                or type(source.get('table_id')) is not int or source['table_id'] != obs.table_id
                or not _same_value(source.get('timestamp'), obs.timestamp)
                or source.get('hand_id') != obs.hand_id
                or source.get('human_confirmed') is not True):
            raise ValueError('Reviewed observation/provenance identity mismatch')
        evidence = source.get('evidence')
        if not isinstance(evidence, list) or len(evidence) > len(_OCR_FIELDS):
            raise ValueError('Invalid reviewed evidence list')
        bound = {}
        for item in evidence:
            if not isinstance(item, dict) or item.get('field') not in _OCR_FIELDS:
                raise ValueError('Unknown reviewed OCR evidence field')
            name = item['field']
            target = _OCR_FIELDS[name]
            idx = item.get('candidate_index')
            if (name in bound or type(idx) is not int or idx < 0
                    or idx in seen_candidates):
                raise ValueError('Duplicate or invalid OCR candidate binding')
            seen_candidates.add(idx)
            t = item.get('source_timestamp')
            if (type(t) not in (float, int) or not math.isfinite(t)
                    or t != obs.timestamp):
                raise ValueError('OCR frame must match reviewed decoded timestamp')
            if item.get('source_timestamp_semantics') != semantics:
                raise ValueError('OCR PTS semantics mismatch')
            if not _same_value(item.get('approved_value'), getattr(obs, target)):
                raise ValueError('OCR reviewed value differs from observation')
            if (type(item.get('reviewer_confidence')) not in (int, float)
                    or not math.isfinite(item['reviewer_confidence'])
                    or item['reviewer_confidence'] != obs.field_confidence.get(target)):
                raise ValueError('OCR reviewer confidence mismatch')
            path = _source_image(item.get('source_image'))
            bound[name] = {'candidate_index': idx, 'source_image': path,
                           'source_timestamp': t, 'field': name,
                           'reviewer_confidence_subjective': item['reviewer_confidence']}
        for name, target in _OCR_FIELDS.items():
            if (getattr(obs, target) is not None) != (name in bound):
                raise ValueError(f'Observed {name} lacks exact reviewed OCR provenance')
        provenance_by_index[index] = bound
        observations.append(obs)
    snapshots = build_decision_snapshots(observations, min_confidence=min_confidence,
                                         max_age_seconds=max_age_seconds)
    for task in snapshots['tasks']:
        index = task['decision_observation_index']
        task['action_source'] = {'observation_index': index,
                                 'source_type': 'human_annotated_action_not_ocr_verified'}
        task['reviewed_ocr_sources'] = {}
        for field, hint in task['visible_hints_unverified'].items():
            if hint is None:
                task['reviewed_ocr_sources'][field] = None
                continue
            src_index = hint['source_observation_index']
            if not observations[src_index].timestamp < task['decision_timestamp']:
                raise ValueError('Future/same-frame information in decision hint')
            refs = provenance_by_index[src_index]
            if field not in refs:
                raise ValueError('Decision hint has no reviewed OCR source')
            task['reviewed_ocr_sources'][field] = dict(refs[field],
                source_observation_index=src_index)
        task['ready_for_ev'] = False
        task['human_confirmed'] = False
    snapshots.update({
        'analysis_status': 'reviewed_activity_decision_queue_not_ev_ready',
        'source_review_sha256': digest,
        'recording_sha256': reviewed['recording_sha256'],
        'evidence_manifest_sha256': reviewed['evidence_manifest_sha256'],
        'ocr_report_sha256': reviewed['ocr_report_sha256'],
        'timestamp_semantics': semantics,
        'ready_for_equity_or_ev': False,
        'warning': ('Frame OCR fields were reviewed by humans but actions and decision contexts '
                    'remain unverified review hints. No opponent ranges, call amounts, hidden '
                    'cards, equity or EV were inferred. Confidence is subjective, not calibrated. '
                    'Re-audit original video/image bytes before trusting upstream evidence.'),
    })
    return snapshots


def run_activity_snapshot_queue(review_path, output_path, *, expected_review_sha256=None,
                                min_confidence=.75, max_age_seconds=30.):
    source, destination = Path(review_path), Path(output_path)
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError('Output must be a new file distinct from input')
    report = json.loads(source.read_text(encoding='utf-8'))
    result = build_activity_snapshot_queue(report,
                expected_review_sha256=expected_review_sha256,
                min_confidence=min_confidence, max_age_seconds=max_age_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_activity_json')
    parser.add_argument('output_json')
    parser.add_argument('--expected-review-sha256')
    parser.add_argument('--min-confidence', type=float, default=.75)
    parser.add_argument('--max-age', type=float, default=30.)
    args = parser.parse_args()
    result = run_activity_snapshot_queue(args.reviewed_activity_json, args.output_json,
        expected_review_sha256=args.expected_review_sha256,
        min_confidence=args.min_confidence, max_age_seconds=args.max_age)
    print(json.dumps(result['counts']))
