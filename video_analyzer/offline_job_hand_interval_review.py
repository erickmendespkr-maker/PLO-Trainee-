"""Manual *nominal* interval annotations for offline PLO video review.

These intervals are navigation annotations, NOT exact source PTS hand boundaries,
reconstructed hands, equity/EV inputs, or authorization to select clips.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from offline_job_review_decisions import load_submission
from offline_job_review_timeline import timeline_job
from offline_job_review_windows import build_windows

JOB_ID = re.compile(r'[0-9a-f]{32}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
MAX_INTERVALS = 2000
MAX_INTERVAL_SECONDS = 600
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SUBMISSION_KEYS = {'schema_version', 'job_id', 'source_windows_sha256', 'reviewer', 'intervals'}
INTERVAL_KEYS = {'table_id', 'hand_label', 'start_nominal_seconds',
                 'end_nominal_seconds', 'reviewer_confidence_subjective', 'reviewer_notes'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _text(value, name, minimum, maximum):
    _require(type(value) is str and minimum <= len(value) <= maximum
             and value == value.strip() and all(ord(c) >= 32 or c in '\n\t' for c in value),
             'Invalid ' + name)
    return value


def _number(value, maximum):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def _windows(timeline, gap_seconds, max_span_seconds):
    windows = build_windows(timeline, gap_seconds=gap_seconds, max_span_seconds=max_span_seconds)
    return windows, hashlib.sha256(_canonical(windows)).hexdigest()


def template(timeline, *, gap_seconds=15, max_span_seconds=120):
    """Blank submission; a navigation window is never auto-promoted to a hand."""
    windows, digest = _windows(timeline, gap_seconds, max_span_seconds)
    return {'schema_version': 1, 'job_id': windows['job_id'],
            'source_windows_sha256': digest, 'reviewer': '', 'intervals': []}


def validate_hand_intervals(timeline, submission, *, gap_seconds=15, max_span_seconds=120):
    """Bind human-entered nominal intervals to freshly validated OCR windows."""
    windows, digest = _windows(timeline, gap_seconds, max_span_seconds)
    _require(type(submission) is dict and set(submission) == SUBMISSION_KEYS,
             'Invalid submission structure')
    _require(type(submission['schema_version']) is int and submission['schema_version'] == 1,
             'Invalid submission schema')
    _require(submission['job_id'] == windows['job_id'] and
             type(submission['job_id']) is str and JOB_ID.fullmatch(submission['job_id']) is not None,
             'Job ID mismatch')
    _require(type(submission['source_windows_sha256']) is str and
             SHA.fullmatch(submission['source_windows_sha256']) is not None and
             submission['source_windows_sha256'] == digest, 'Window digest mismatch')
    reviewer = _text(submission['reviewer'], 'reviewer', 2, 80)
    intervals = submission['intervals']
    _require(type(intervals) is list and len(intervals) <= MAX_INTERVALS, 'Invalid interval count')

    by_table = {table: [] for table in range(1, 5)}
    for window in windows['windows']:
        for key in window['observation_keys']:
            by_table[window['table_id']].append((float(key['nominal_timestamp_seconds']),
                                                window['window_id'], key,
                                                window['has_unresolved_observations']))
    times = {}
    for table, rows in by_table.items():
        rows.sort(key=lambda r: (r[0], r[2]['candidate_index'], r[2]['field']))
        times[table] = [r[0] for r in rows]

    seen_labels, last_end, linked = set(), {}, set()
    result_intervals = []
    # Sorting ensures overlap is rejected independently of the submitted order.
    validated = []
    for item in intervals:
        _require(type(item) is dict and set(item) == INTERVAL_KEYS,
                 'Invalid interval structure')
        table = item['table_id']
        label = item['hand_label']
        start = item['start_nominal_seconds']
        end = item['end_nominal_seconds']
        confidence = item['reviewer_confidence_subjective']
        _require(type(table) is int and table in by_table, 'Invalid table')
        _require(type(label) is str and LABEL.fullmatch(label) is not None,
                 'Invalid hand label')
        _require((table, label) not in seen_labels, 'Duplicate hand label')
        seen_labels.add((table, label))
        _require(_number(start, 86400) and _number(end, 86400) and
                 start < end and end - start <= MAX_INTERVAL_SECONDS, 'Invalid nominal interval')
        _require(_number(confidence, 1), 'Invalid subjective confidence')
        notes = _text(item['reviewer_notes'], 'reviewer notes', 5, 500)
        validated.append((table, float(start), float(end), label, float(confidence), notes))

    for table, start, end, label, confidence, notes in sorted(validated):
        _require(table not in last_end or start > last_end[table],
                 'Overlapping or touching nominal intervals')
        last_end[table] = end
        first = bisect_left(times[table], start)
        stop = bisect_right(times[table], end)
        selected = by_table[table][first:stop]
        _require(bool(selected), 'Interval has no observed OCR evidence')
        for row in selected:
            key = (table, row[0], row[2]['field'], row[2]['candidate_index'])
            _require(key not in linked, 'Observation assigned twice')
            linked.add(key)
        result_intervals.append({
            'table_id': table, 'hand_label_human_assigned': label,
            'start_nominal_seconds_human_marked': start,
            'end_nominal_seconds_human_marked': end,
            'reviewer_confidence_subjective': confidence, 'reviewer_notes': notes,
            'observation_count': len(selected),
            'observation_keys': [row[2] for row in selected],
            'source_navigation_window_ids': sorted({row[1] for row in selected}),
            'linked_window_has_unresolved_observations': any(row[3] for row in selected),
            'hand_start_or_end_pts_verified': False,
            'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'human_nominal_hand_intervals_not_reconstructed_hands',
        'job_id': windows['job_id'], 'source_sha256': windows['source_sha256'],
        'source_windows_sha256': digest,
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'reviewer': reviewer, 'intervals': result_intervals,
        'counts': {'human_marked_intervals': len(result_intervals),
                   'linked_ocr_observations': len(linked),
                   'unassigned_ocr_observations': windows['observation_count'] - len(linked)},
        'requires_manual_hand_reconstruction': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Human-marked nominal intervals are navigation annotations, not exact source PTS.',
            'OCR observations may be incomplete or wrong even after human review.',
            'A navigation window may contain multiple hands; gaps may hide hands.',
            'No reconstructed hands, equity, EV, automatic clips, or strategic verdicts.',
        ],
    }


def review_job(store, job_id, results_root, submission, *, gap_seconds=15, max_span_seconds=120):
    _require(type(job_id) is str and JOB_ID.fullmatch(job_id) is not None, 'Invalid job ID')
    timeline = timeline_job(store, job_id, results_root)  # Re-audits source, frames, and human OCR report.
    return validate_hand_intervals(timeline, submission, gap_seconds=gap_seconds,
                                   max_span_seconds=max_span_seconds)


def export_review(store, job_id, results_root, submission, *, gap_seconds=15,
                  max_span_seconds=120):
    report = review_job(store, job_id, results_root, submission,
                        gap_seconds=gap_seconds, max_span_seconds=max_span_seconds)
    folder = Path(results_root) / job_id
    _require(folder.is_dir() and not folder.is_symlink(), 'Unsafe output directory')
    data = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
    _require(len(data) <= MAX_OUTPUT_BYTES, 'Report exceeds size limit')
    target = folder / 'human_nominal_hand_intervals.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output file')
            stream.write(data)
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
    parser.add_argument('--submission')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--gap-seconds', type=float, default=15)
    parser.add_argument('--max-span-seconds', type=float, default=120)
    args = parser.parse_args(argv)
    _require(not args.export or args.submission is not None, 'Export requires submission')
    from offline_jobs import OfflineJobStore
    store = OfflineJobStore(args.database)
    if args.submission is None:
        result = template(timeline_job(store, args.job_id, args.results_root),
                          gap_seconds=args.gap_seconds, max_span_seconds=args.max_span_seconds)
    else:
        submission = load_submission(args.submission)
        fn = export_review if args.export else review_job
        result = fn(store, args.job_id, args.results_root, submission,
                    gap_seconds=args.gap_seconds, max_span_seconds=args.max_span_seconds)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
