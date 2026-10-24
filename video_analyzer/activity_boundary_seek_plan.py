"""Review-only FFmpeg seek plan for human-assigned inter-hand intervals.

Bridges activity_hand_boundary_review output to activity_evidence_export. Planned
seeks are *not* decoded PTS, exact boundaries, OCR facts, or poker decisions.
Never infer hands or authorize clips, equity, EV, or strategic-error claims.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256
from video_validator import validate_recording

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_STATUS = 'review_only_candidate_inter_hand_windows'


def _finite(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def _digest(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _check_review(review, recording_sha256, duration, expected_review_sha256):
    if (not isinstance(review, dict) or review.get('schema_version') != 1
            or review.get('analysis_status') != _STATUS
            or review.get('ready_for_equity_or_ev') is not False
            or review.get('automatic_hand_boundaries_authorized') is not False
            or review.get('automatic_clip_selection_authorized') is not False
            or review.get('strategic_error_established') is not False
            or not _digest(review.get('recording_sha256'))
            or not _digest(review.get('source_timeline_sha256'))
            or not _digest(review.get('source_review_sha256'))
            or review['recording_sha256'] != recording_sha256
            or 'decoded' not in str(review.get('timestamp_semantics', '')).lower()):
        raise ValueError('Incompatible review report or recording identity')
    if expected_review_sha256 is not None:
        if not _digest(expected_review_sha256) or canonical_sha256(review) != expected_review_sha256:
            raise ValueError('Review report SHA-256 mismatch')
    windows = review.get('inter_hand_review_windows')
    spans = review.get('observed_hand_spans')
    counts = review.get('counts')
    if (not isinstance(windows, list) or not isinstance(spans, list)
            or not isinstance(counts, dict) or len(windows) > 10000
            or len(spans) > 10000
            or counts.get('inter_hand_windows') != len(windows)
            or counts.get('observed_human_assigned_hands') != len(spans)
            or counts.get('windows_needing_manual_resolution') != sum(
                isinstance(w, dict) and w.get('status') == 'manual_resolution_required'
                for w in windows)):
        raise ValueError('Inconsistent boundary review counts')
    known = {}
    for span in spans:
        if (not isinstance(span, dict) or type(span.get('table_id')) is not int
                or not 1 <= span['table_id'] <= 4
                or not isinstance(span.get('hand_id_human_assigned'), str)
                or not span['hand_id_human_assigned'].strip()
                or not _finite(span.get('first_observed_pts'))
                or not _finite(span.get('last_observed_pts'))
                or span['first_observed_pts'] > span['last_observed_pts']
                or span['last_observed_pts'] > duration + 1e-6):
            raise ValueError('Invalid observed hand span')
        key = (span['table_id'], span['hand_id_human_assigned'])
        if key in known:
            raise ValueError('Duplicate hand span')
        known[key] = span
    seen_pairs = set()
    for window in windows:
        if (not isinstance(window, dict) or type(window.get('table_id')) is not int
                or not 1 <= window['table_id'] <= 4
                or window.get('exact_boundary_known') is not False
                or window.get('hand_assignment_automated') is not False
                or window.get('status') not in ('review_interval_available_not_confirmed',
                                                'manual_resolution_required')
                or not isinstance(window.get('review_reasons'), list)
                or not isinstance(window.get('unassigned_observation_indices'), list)
                or not isinstance(window.get('unverified_ocr_hints'), list)
                or not _finite(window.get('previous_last_observed_pts'))
                or not _finite(window.get('next_first_observed_pts'))):
            raise ValueError('Invalid or automatically confirmed boundary window')
        table = window['table_id']
        prev, nxt = window.get('previous_hand_id_human_assigned'), window.get('next_hand_id_human_assigned')
        if (not isinstance(prev, str) or not isinstance(nxt, str) or prev == nxt
                or (table, prev) not in known or (table, nxt) not in known):
            raise ValueError('Unknown adjacent human-assigned hands')
        pair = (table, prev, nxt)
        if pair in seen_pairs:
            raise ValueError('Duplicate adjacent-hand window')
        seen_pairs.add(pair)
        start, end = window['previous_last_observed_pts'], window['next_first_observed_pts']
        if (start != known[(table, prev)]['last_observed_pts']
                or end != known[(table, nxt)]['first_observed_pts']):
            raise ValueError('Review interval does not match observed hand spans')
        interval = window.get('candidate_interval_pts')
        if start < end:
            if (interval != [start, end] or end > duration + 1e-6
                    or not _finite(window.get('gap_seconds'))
                    or not math.isclose(window['gap_seconds'], end-start, abs_tol=1e-6)):
                raise ValueError('Inconsistent positive review interval')
        elif (interval is not None or window.get('gap_seconds') != (0 if start == end else None)):
            raise ValueError('Overlapping/equal hands cannot yield a seek interval')
        if (window['status'] == 'review_interval_available_not_confirmed'
                and window['review_reasons']):
            raise ValueError('Review-required window mislabelled as clear')
        if (window['status'] == 'manual_resolution_required'
                and not window['review_reasons']):
            raise ValueError('Missing manual resolution reasons')
    return windows


def build_boundary_seek_plan(review, *, recording_sha256, duration_seconds,
                             expected_review_sha256=None, samples_per_window=3,
                             min_spacing_seconds=0.05, max_total_requests=600):
    """Plan bounded, strictly interior seek times for human review only.

    Intervals without positive width are skipped, not guessed. All proposed
    timestamps remain requested seeks; FFmpeg may decode later source PTS.
    """
    if not _digest(recording_sha256) or not _finite(duration_seconds, positive=True):
        raise ValueError('Invalid recording identity or duration')
    if (type(samples_per_window) is not int or not 1 <= samples_per_window <= 5
            or not _finite(min_spacing_seconds, positive=True)
            or min_spacing_seconds > 30
            or type(max_total_requests) is not int or not 1 <= max_total_requests <= 600):
        raise ValueError('Invalid bounded sampling parameters')
    windows = _check_review(review, recording_sha256, duration_seconds, expected_review_sha256)
    per_table = {i: [] for i in range(1, 5)}
    associations, skipped = [], []
    for index, window in enumerate(windows):
        interval = window['candidate_interval_pts']
        if interval is None:
            skipped.append({'review_window_index': index, 'reason': 'no_positive_review_interval'})
            continue
        start, end = interval
        table = window['table_id']
        candidates = [round(start + (end-start)*(j+1)/(samples_per_window+1), 6)
                      for j in range(samples_per_window)]
        chosen = []
        for t in candidates:
            if not start < t < end or not t < duration_seconds:
                continue
            if any(abs(t - existing) < min_spacing_seconds - 1e-9
                   for existing in per_table[table]):
                continue
            if len(per_table[table]) + sum(map(len, (per_table[k] for k in range(1, 5) if k != table))) >= max_total_requests:
                raise ValueError('Boundary seek plan exceeds extraction budget')
            per_table[table].append(t)
            chosen.append(t)
        if not chosen:
            skipped.append({'review_window_index': index, 'reason': 'no_distinct_interior_seek'})
        associations.append({'review_window_index': index, 'table_id': table,
                             'candidate_interval_pts': [start, end],
                             'requested_seek_seconds': chosen,
                             'status': 'unverified_review_only_not_hand_boundary'})
    tables = []
    for table, times in per_table.items():
        if times:
            times.sort()
            tables.append({'table_id': table, 'planned_count': len(times),
                           'requested_frames': [
                               {'requested_seek_seconds': t,
                                'reason': 'unverified_activity_neighborhood'}
                               for t in times]})
    if not tables:
        raise ValueError('No valid interior review seeks; manual boundary review required')
    return {
        'schema_version': 1,
        'analysis_status': 'requested_offline_seek_plan_only',
        'timestamp_semantics': 'requested_seek_seconds_not_decoded_source_pts',
        'requires_manual_review': True,
        'recording_sha256': recording_sha256,
        'duration_seconds': float(duration_seconds),
        'source_boundary_review_sha256': canonical_sha256(review),
        'source_timeline_sha256': review['source_timeline_sha256'],
        'planned_total_frames': sum(len(v) for v in per_table.values()),
        'tables': tables,
        'review_window_seek_associations': associations,
        'skipped_review_windows': skipped,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'ready_for_equity_or_ev': False,
        'strategic_error_established': False,
        'warning': ('Requested FFmpeg seek times inside human-reviewed intervals are not '
                    'decoded PTS, exact hand boundaries or confirmed poker actions. '
                    'Audit extracted PNG hashes and require manual review.'),
    }


def write_boundary_seek_plan(review_path, recording_path, output_path, **kwargs):
    """Verify actual local MP4/WebM identity; write a new JSON, never overwrite."""
    review_path, recording_path, output_path = map(Path, (review_path, recording_path, output_path))
    if (any(p.is_symlink() or not p.is_file() for p in (review_path, recording_path))
            or output_path.exists() or output_path.is_symlink()):
        raise ValueError('Require regular inputs and a new output path')
    info = validate_recording(recording_path)
    h = hashlib.sha256()
    with recording_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    review = json.loads(review_path.read_text(encoding='utf-8'))
    plan = build_boundary_seek_plan(review, recording_sha256=h.hexdigest(),
                                    duration_seconds=info['duration_seconds'], **kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boundary_review_json')
    parser.add_argument('recording_mp4_or_webm')
    parser.add_argument('output_seek_plan_json')
    parser.add_argument('--expected-review-sha256')
    parser.add_argument('--samples-per-window', type=int, default=3)
    parser.add_argument('--max-total-requests', type=int, default=600)
    args = parser.parse_args()
    result = write_boundary_seek_plan(
        args.boundary_review_json, args.recording_mp4_or_webm,
        args.output_seek_plan_json,
        expected_review_sha256=args.expected_review_sha256,
        samples_per_window=args.samples_per_window,
        max_total_requests=args.max_total_requests)
    print(json.dumps({'planned_total_frames': result['planned_total_frames'],
                      'skipped_review_windows': len(result['skipped_review_windows'])}))
