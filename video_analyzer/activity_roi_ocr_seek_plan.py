"""Bounded offline resampling plan for OCR of unverified visual ROI changes.

The low-resolution contact-sheet comparison identifies *where to look*, not
what the pixels mean. This adapter requests full-resolution table crops from
the original recording via activity_evidence_export, so existing OCR tooling
can inspect board/hero_cards/pot regions configured by a human. It never
infers a poker action, verifies a card, or assigns a hand.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256
from video_validator import validate_recording

_HEX = re.compile(r'[0-9a-f]{64}\Z')
_IMAGE = re.compile(r'images/table_(0[1-4])/frame_\d{5}\.png\Z')
_LABELS = ('board', 'hero_cards', 'pot')
_BLOCKED = ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
            'automatic_clip_selection_authorized', 'strategic_error_established')


def _number(x):
    return type(x) in (int, float) and math.isfinite(x)


def _digest(x):
    return isinstance(x, str) and _HEX.fullmatch(x) is not None


def _validate_queue(queue, recording_sha256, duration, expected_queue_sha256):
    if (not isinstance(queue, dict) or queue.get('schema_version') != 1
            or queue.get('analysis_status') != 'unverified_region_pixel_review_queue'
            or queue.get('timestamp_semantics') != 'decoded_source_pts_seconds_not_exact_hand_boundary'
            or queue.get('requires_manual_review') is not True
            or any(queue.get(flag) is not False for flag in _BLOCKED)
            or not _digest(queue.get('recording_sha256'))
            or queue['recording_sha256'] != recording_sha256
            or any(not _digest(queue.get(key)) for key in (
                'source_region_change_hints_sha256', 'source_contact_sheet_sha256',
                'source_region_profile_sha256'))
            or queue.get('ranking_method') != 'descending_peak_mean_absolute_luma_difference_only'):
        raise ValueError('Unsafe ROI queue or recording identity')
    if expected_queue_sha256 is not None and (
            not _digest(expected_queue_sha256)
            or canonical_sha256(queue) != expected_queue_sha256):
        raise ValueError('ROI queue SHA-256 mismatch')
    rows = queue.get('candidates')
    if (not isinstance(rows, list) or len(rows) > 1000
            or type(queue.get('max_candidates')) is not int
            or not 1 <= queue['max_candidates'] <= 1000
            or len(rows) > queue['max_candidates']
            or type(queue.get('total_candidate_intervals')) is not int
            or type(queue.get('omitted_due_to_budget')) is not int
            or queue['omitted_due_to_budget'] < 0
            or queue['total_candidate_intervals'] != len(rows) + queue['omitted_due_to_budget']):
        raise ValueError('Invalid ROI queue counts')
    previous_peak = float('inf')
    for rank, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or type(row.get('pixel_review_rank')) is not int
                or row['pixel_review_rank'] != rank
                or type(row.get('table_id')) is not int or not 1 <= row['table_id'] <= 4
                or type(row.get('review_window_index')) is not int
                or row['review_window_index'] < 0
                or row.get('region_label_hypothesis') not in _LABELS
                or not _number(row.get('start_pts_seconds'))
                or not _number(row.get('end_pts_seconds'))
                or not 0 <= row['start_pts_seconds'] < row['end_pts_seconds'] <= duration + 1e-6
                or not _number(row.get('peak_luma_difference'))
                or not 0 <= row['peak_luma_difference'] <= 1
                or row['peak_luma_difference'] > previous_peak
                or type(row.get('comparison_count')) is not int or row['comparison_count'] < 1
                or row.get('confidence_in_region_mapping') != 'not_calibrated'
                or row.get('confidence_in_poker_semantics') != 'not_calibrated'
                or row.get('requires_manual_review') is not True
                or not isinstance(row.get('first_frame'), str)
                or not isinstance(row.get('last_frame'), str)
                or not _IMAGE.fullmatch(row['first_frame'])
                or not _IMAGE.fullmatch(row['last_frame'])
                or int(row['first_frame'][13:15]) != row['table_id']
                or int(row['last_frame'][13:15]) != row['table_id']):
            raise ValueError('Invalid unverified ROI candidate')
        previous_peak = row['peak_luma_difference']
    return rows


def build_roi_ocr_seek_plan(queue, *, recording_sha256, duration_seconds,
                            expected_queue_sha256=None, samples_per_candidate=3,
                            max_total_requests=600):
    """Create a bounded *requested-seek* plan, not recognized poker evidence.

    Candidate priority is solely pixel intensity. Multiple ROI candidates can
    reuse one table/PTS request. Quantization can collapse closely spaced seeks;
    this is reported rather than pretending independent frames were observed.
    """
    if (not _digest(recording_sha256) or not _number(duration_seconds)
            or duration_seconds <= 0 or type(samples_per_candidate) is not int
            or not 1 <= samples_per_candidate <= 5
            or type(max_total_requests) is not int
            or not 1 <= max_total_requests <= 600):
        raise ValueError('Invalid source or extraction budget')
    rows = _validate_queue(queue, recording_sha256, duration_seconds,
                           expected_queue_sha256)
    times = {table: set() for table in range(1, 5)}
    selected, skipped = [], []
    for row in rows:
        start, end = row['start_pts_seconds'], row['end_pts_seconds']
        # Interior points only; no claim of an exact visual transition time.
        proposals = [round(start + (end - start) * (i + 1) /
                           (samples_per_candidate + 1), 6)
                     for i in range(samples_per_candidate)]
        proposals = sorted({t for t in proposals if 0 <= t < duration_seconds
                            and start < t < end})
        table = row['table_id']
        new = [t for t in proposals if t not in times[table]]
        if sum(map(len, times.values())) + len(new) > max_total_requests:
            skipped.append({'pixel_review_rank': row['pixel_review_rank'],
                            'reason': 'request_budget_exhausted',
                            'region_label_hypothesis': row['region_label_hypothesis'],
                            'table_id': table})
            continue
        times[table].update(new)
        selected.append({'pixel_review_rank': row['pixel_review_rank'],
                         'table_id': table,
                         'region_label_hypothesis_unverified': row['region_label_hypothesis'],
                         'candidate_interval_pts': [start, end],
                         'requested_seek_seconds': proposals,
                         'new_unique_table_seeks': len(new),
                         'status': 'ocr_review_resampling_only_not_recognized_event'})
        if not proposals:
            skipped.append({'pixel_review_rank': row['pixel_review_rank'],
                            'reason': 'no_distinct_interior_seek',
                            'region_label_hypothesis': row['region_label_hypothesis'],
                            'table_id': table})
    tables = [{'table_id': table, 'planned_count': len(values),
               'requested_frames': [{'requested_seek_seconds': t,
                                     'reason': 'unverified_activity_neighborhood'}
                                    for t in sorted(values)]}
              for table, values in times.items() if values]
    if not tables:
        raise ValueError('No valid resampling requests; review ROI queue manually')
    return {'schema_version': 1,
            'analysis_status': 'requested_offline_seek_plan_only',
            'timestamp_semantics': 'requested_seek_seconds_not_decoded_source_pts',
            'requires_manual_review': True,
            'recording_sha256': recording_sha256,
            'duration_seconds': float(duration_seconds),
            'source_roi_queue_sha256': canonical_sha256(queue),
            'source_region_profile_sha256': queue['source_region_profile_sha256'],
            'source_contact_sheet_sha256': queue['source_contact_sheet_sha256'],
            'source_region_change_hints_sha256': queue['source_region_change_hints_sha256'],
            'selection_method': 'interior_uniform_seeks_of_ranked_uncalibrated_roi_changes',
            'samples_per_candidate': samples_per_candidate,
            'max_total_requests': max_total_requests,
            'planned_total_frames': sum(len(v) for v in times.values()),
            'tables': tables,
            'candidate_seek_associations': selected,
            'skipped_candidates': skipped,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'ready_for_equity_or_ev': False,
            'strategic_error_established': False,
            'warning': ('Pixel intensity only chooses OCR inspection times. Requested seeks are '
                        'not decoded PTS. Region names are manual hypotheses; OCR guesses '
                        'require human verification. No hands, cards, actions, EV, or errors confirmed.')}


def write_roi_ocr_seek_plan(queue_json, recording_path, output_json, **kwargs):
    queue_path, source, destination = map(Path, (queue_json, recording_path, output_json))
    if (queue_path.is_symlink() or source.is_symlink() or destination.is_symlink()
            or not queue_path.is_file() or not source.is_file() or destination.exists()
            or destination.resolve() in (queue_path.resolve(), source.resolve())):
        raise ValueError('Require regular inputs and new output path')
    info = validate_recording(source)
    h = hashlib.sha256()
    with source.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    result = build_roi_ocr_seek_plan(queue, recording_sha256=h.hexdigest(),
                                     duration_seconds=info['duration_seconds'], **kwargs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roi_queue_json')
    parser.add_argument('recording_mp4_or_webm')
    parser.add_argument('output_seek_plan_json')
    parser.add_argument('--expected-queue-sha256')
    parser.add_argument('--samples-per-candidate', type=int, default=3)
    parser.add_argument('--max-total-requests', type=int, default=600)
    args = parser.parse_args()
    result = write_roi_ocr_seek_plan(
        args.roi_queue_json, args.recording_mp4_or_webm, args.output_seek_plan_json,
        expected_queue_sha256=args.expected_queue_sha256,
        samples_per_candidate=args.samples_per_candidate,
        max_total_requests=args.max_total_requests)
    print(json.dumps({'planned_total_frames': result['planned_total_frames'],
                      'selected_candidates': len(result['candidate_seek_associations']),
                      'skipped_candidates': len(result['skipped_candidates'])}))
