"""Auditable per-interval OCR evidence dossiers for recorded PLO5/PLO6 sessions.

This is a conservative bridge from human-marked *nominal* intervals to a
manual hand-history worksheet. It does NOT reconstruct hands, parse OCR as
cards/amounts, attest video PTS, or authorize equity, EV, or clip selection.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from offline_job_hand_interval_review import validate_hand_intervals
from offline_job_review_decisions import load_submission
from offline_job_review_timeline import timeline_job

FIELDS = ('hero_cards', 'board', 'pot', 'bet')
STATUSES = ('confirmed', 'corrected', 'uncertain', 'rejected', 'pending')
MAX_DOSSIERS = 2000
MAX_OBSERVATIONS = 20_000
MAX_BYTES = 16 * 1024 * 1024
JOB_ID = re.compile(r'[0-9a-f]{32}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _key(obs):
    return (obs['table_id'], float(obs['nominal_timestamp_seconds']),
            obs['field'], obs['candidate_index'], obs['source_image_sha256'])


def build_dossiers(timeline, interval_submission, *, gap_seconds=15, max_span_seconds=120):
    """Build structured evidence from a *validated* timeline and human intervals.

    For authentic provenance call dossiers_job(), which re-audits original
    recording, worker output, OCR candidates and saved human OCR decisions.
    Direct use is intended for deterministic tests and offline inspection.
    """
    intervals = validate_hand_intervals(timeline, interval_submission,
                                        gap_seconds=gap_seconds,
                                        max_span_seconds=max_span_seconds)
    _require(intervals['analysis_status'] ==
             'human_nominal_hand_intervals_not_reconstructed_hands',
             'Unexpected interval status')
    for flag in ('hand_reconstruction_verified', 'ready_for_equity_or_ev',
                 'automatic_clip_selection_authorized'):
        _require(intervals.get(flag) is False, 'Interval authority gate violated')
    _require(type(timeline.get('observations')) is list and
             len(timeline['observations']) <= MAX_OBSERVATIONS, 'Invalid timeline size')
    indexed = {}
    for row in timeline['observations']:
        _require(type(row) is dict and row.get('field') in FIELDS,
                 'Unknown or malformed OCR field')
        _require(row.get('review_status') in STATUSES and
                 type(row.get('review_status')) is str, 'Invalid OCR status')
        _require(row.get('hand_reconstruction_verified') is False and
                 row.get('ready_for_equity_or_ev') is False, 'OCR authority gate violated')
        key = _key(row)
        _require(key not in indexed, 'Duplicate evidence identity')
        indexed[key] = row

    linked = set()
    dossiers = []
    _require(len(intervals['intervals']) <= MAX_DOSSIERS, 'Too many intervals')
    for span in intervals['intervals']:
        table = span['table_id']
        selected = []
        for reference in span['observation_keys']:
            key = (table, float(reference['nominal_timestamp_seconds']),
                   reference['field'], reference['candidate_index'],
                   reference['source_image_sha256'])
            _require(key in indexed and key not in linked, 'Stale or duplicate observation reference')
            linked.add(key)
            obs = indexed[key]
            selected.append({
                'table_id': table,
                'nominal_timestamp_seconds': float(obs['nominal_timestamp_seconds']),
                'field': obs['field'], 'candidate_index': obs['candidate_index'],
                'source_image': obs['source_image'],
                'source_image_sha256': obs['source_image_sha256'],
                'original_ocr_text_unverified': obs['original_ocr_text_unverified'],
                'review_status': obs['review_status'],
                'human_annotation_value_unparsed': obs['human_annotation_value'],
                'human_confidence_subjective': obs['human_confidence_subjective'],
                'review_reason': obs['review_reason'],
                'reviewer': obs['reviewer'],
            })
        selected.sort(key=lambda x: (x['nominal_timestamp_seconds'], x['candidate_index'], x['field']))
        _require(len(selected) == span['observation_count'], 'Interval observation count mismatch')
        summaries = {}
        unresolved = False
        simultaneous_conflicts = []
        changing_fields = []
        for field in FIELDS:
            field_rows = [row for row in selected if row['field'] == field]
            statuses = {s: sum(row['review_status'] == s for row in field_rows) for s in STATUSES}
            approved = [row for row in field_rows if row['review_status'] in ('confirmed', 'corrected')]
            # Different pots/boards across timestamps are expected in poker;
            # do NOT call temporal variation a contradiction.
            distinct = sorted({row['human_annotation_value_unparsed'] for row in approved})
            if len(distinct) > 1:
                changing_fields.append(field)
            at_time = defaultdict(set)
            for row in approved:
                at_time[row['nominal_timestamp_seconds']].add(row['human_annotation_value_unparsed'])
            conflicting_stamps = sorted(stamp for stamp, values in at_time.items() if len(values) > 1)
            if conflicting_stamps:
                simultaneous_conflicts.append(field)
            if any(statuses[s] for s in ('uncertain', 'rejected', 'pending')):
                unresolved = True
            summaries[field] = {
                'observation_count': len(field_rows),
                'review_status_counts': statuses,
                'human_approved_observation_count': len(approved),
                'distinct_human_values_unparsed': distinct,
                'multiple_values_across_time_requires_interpretation': len(distinct) > 1,
                'same_nominal_timestamp_conflicts': conflicting_stamps,
                'missing_from_interval': not field_rows,
                'usable_as_mathematical_fact': False,
            }
        flags = []
        if unresolved:
            flags.append('unresolved_ocr_observations')
        if simultaneous_conflicts:
            flags.append('different_human_values_same_field_and_nominal_timestamp')
        if changing_fields:
            flags.append('temporal_value_changes_require_action_sequence_review')
        if any(summaries[f]['missing_from_interval'] for f in FIELDS):
            flags.append('missing_ocr_field_observations')
        flags.extend(('nominal_boundaries_not_verified_pts',
                      'actions_stacks_ranges_not_reconstructed'))
        dossiers.append({
            'table_id': table,
            'hand_label_human_assigned': span['hand_label_human_assigned'],
            'start_nominal_seconds_human_marked': span['start_nominal_seconds_human_marked'],
            'end_nominal_seconds_human_marked': span['end_nominal_seconds_human_marked'],
            'reviewer_confidence_subjective': span['reviewer_confidence_subjective'],
            'reviewer_notes': span['reviewer_notes'],
            'source_navigation_window_ids': span['source_navigation_window_ids'],
            'observations': selected,
            'field_summaries': summaries,
            'quality_flags': flags,
            'manual_reconstruction_worksheet': {
                'hero_cards': None, 'board': None, 'pot': None, 'bet': None,
                'stacks': None, 'action_sequence': None, 'opponent_ranges': None,
                'decision_point': None, 'exact_source_pts': None,
                'independent_human_attestation': None,
            },
            'hand_start_or_end_pts_verified': False,
            'hand_reconstruction_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        })
    _require(len(linked) == intervals['counts']['linked_ocr_observations'],
             'Linked observation count mismatch')
    _require(len(indexed) - len(linked) == intervals['counts']['unassigned_ocr_observations'],
             'Unassigned observation count mismatch')
    return {
        'schema_version': 1,
        'analysis_status': 'reviewed_nominal_interval_evidence_dossiers_no_math',
        'job_id': intervals['job_id'], 'source_sha256': intervals['source_sha256'],
        'source_timeline_sha256': _digest(timeline),
        'source_intervals_sha256': _digest(intervals),
        'source_windows_sha256': intervals['source_windows_sha256'],
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'dossiers': dossiers,
        'counts': {'dossiers': len(dossiers), 'linked_ocr_observations': len(linked),
                   'unassigned_ocr_observations': len(indexed) - len(linked),
                   'math_ready': 0},
        'requires_manual_hand_reconstruction': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Human-marked intervals are nominal navigation annotations, not source PTS.',
            'Reviewed OCR strings are unparsed observations, not verified cards or monetary amounts.',
            'Different values at different timestamps may be normal progression, not errors.',
            'No complete action sequence, opponent ranges, equity, EV, or strategic verdict.',
        ],
    }


def dossiers_job(store, job_id, results_root, submission, *, gap_seconds=15, max_span_seconds=120):
    _require(type(job_id) is str and JOB_ID.fullmatch(job_id) is not None, 'Invalid job ID')
    timeline = timeline_job(store, job_id, results_root)  # full source and OCR review re-audit
    return build_dossiers(timeline, submission, gap_seconds=gap_seconds,
                          max_span_seconds=max_span_seconds)


def export_dossiers(store, job_id, results_root, submission, *, gap_seconds=15,
                    max_span_seconds=120):
    report = dossiers_job(store, job_id, results_root, submission,
                          gap_seconds=gap_seconds, max_span_seconds=max_span_seconds)
    folder = Path(results_root) / job_id
    _require(folder.is_dir() and not folder.is_symlink(), 'Unsafe output directory')
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
    _require(len(payload) <= MAX_BYTES, 'Report exceeds size limit')
    target = folder / 'human_hand_evidence_dossiers.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output file')
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('job_id')
    parser.add_argument('results_root')
    parser.add_argument('--submission', required=True)
    parser.add_argument('--gap-seconds', type=float, default=15)
    parser.add_argument('--max-span-seconds', type=float, default=120)
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(argv)
    from offline_jobs import OfflineJobStore
    submission = load_submission(args.submission)
    store = OfflineJobStore(args.database)
    fn = export_dossiers if args.export else dossiers_job
    report = fn(store, args.job_id, args.results_root, submission,
                gap_seconds=args.gap_seconds, max_span_seconds=args.max_span_seconds)
    print(json.dumps({'job_id': report['job_id'], 'counts': report['counts'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
