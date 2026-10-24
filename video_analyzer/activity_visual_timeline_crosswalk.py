"""Offline, review-only crosswalk between ROI pixel hints and reviewed hand timelines.

Temporal overlap is not a recognized card, action, hand boundary, or strategy error.
The two upstream pipelines may have DIFFERENT PTS origins. No associations are
made unless a reviewer explicitly supplies an alignment declaration. Such a
declaration is subjective metadata, not proof of accurate synchronization.
"""
import argparse
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_BLOCKED = ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
            'automatic_clip_selection_authorized', 'strategic_error_established')
_LABELS = ('board', 'hero_cards', 'pot')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _check_sources(queue, timeline, expected_queue_sha256, expected_timeline_sha256):
    if not isinstance(queue, dict) or not isinstance(timeline, dict):
        raise ValueError('Expected two JSON reports')
    for report, status in ((queue, 'unverified_region_pixel_review_queue'),
                           (timeline, 'human_reviewed_visible_timeline_not_verified_hand_reconstruction')):
        if (report.get('schema_version') != 1 or report.get('analysis_status') != status
                or any(report.get(flag) is not False for flag in _BLOCKED)
                or not _sha(report.get('recording_sha256'))
                or 'decoded' not in str(report.get('timestamp_semantics', '')).lower()):
            raise ValueError('Unsafe or incompatible upstream report')
    if queue['recording_sha256'] != timeline['recording_sha256']:
        raise ValueError('Different recording SHA-256; refuse cross-video association')
    for report, expected in ((queue, expected_queue_sha256), (timeline, expected_timeline_sha256)):
        if expected is not None and (not _sha(expected) or canonical_sha256(report) != expected):
            raise ValueError('Upstream report SHA-256 mismatch')
    if (queue.get('requires_manual_review') is not True
            or not _sha(queue.get('source_region_change_hints_sha256'))
            or not _sha(queue.get('source_contact_sheet_sha256'))
            or not _sha(queue.get('source_region_profile_sha256'))
            or queue.get('ranking_method') != 'descending_peak_mean_absolute_luma_difference_only'):
        raise ValueError('Invalid ROI queue provenance or review status')
    candidates = queue.get('candidates')
    if (not isinstance(candidates, list) or len(candidates) > 1000
            or type(queue.get('total_candidate_intervals')) is not int
            or type(queue.get('omitted_due_to_budget')) is not int
            or queue['total_candidate_intervals'] != len(candidates) + queue['omitted_due_to_budget']
            or queue['omitted_due_to_budget'] < 0
            or type(queue.get('max_candidates')) not in (int, type(None))
            or (type(queue.get('max_candidates')) is int and
                len(candidates) > queue['max_candidates'])):
        raise ValueError('Invalid ROI queue counts')
    previous_peak = float('inf')
    for rank, item in enumerate(candidates, 1):
        if (not isinstance(item, dict) or item.get('pixel_review_rank') != rank
                or type(item.get('table_id')) is not int or not 1 <= item['table_id'] <= 4
                or type(item.get('review_window_index')) is not int
                or item['review_window_index'] < 0
                or item.get('region_label_hypothesis') not in _LABELS
                or not _number(item.get('start_pts_seconds'))
                or not _number(item.get('end_pts_seconds'))
                or not 0 <= item['start_pts_seconds'] < item['end_pts_seconds']
                or not _number(item.get('peak_luma_difference'))
                or not 0 <= item['peak_luma_difference'] <= 1
                or type(item.get('comparison_count')) is not int
                or item['comparison_count'] < 1
                or item.get('confidence_in_poker_semantics') != 'not_calibrated'
                or item.get('confidence_in_region_mapping') != 'not_calibrated'
                or item.get('requires_manual_review') is not True
                or item['peak_luma_difference'] > previous_peak):
            raise ValueError('Invalid ROI review candidate')
        previous_peak = item['peak_luma_difference']
    hands = timeline.get('hands')
    if not isinstance(hands, list) or len(hands) > 10000:
        raise ValueError('Invalid reviewed timeline hands')
    if (not isinstance(timeline.get('counts'), dict)
            or timeline['counts'].get('hands_human_assigned') != len(hands)
            or not isinstance(timeline.get('unassigned_observations'), list)
            or timeline['counts'].get('unassigned_observations') != len(timeline['unassigned_observations'])
            or type(timeline['counts'].get('observations')) is not int
            or timeline['counts']['observations'] < len(timeline['unassigned_observations'])
            or not _sha(timeline.get('source_review_sha256'))):
        raise ValueError('Inconsistent reviewed timeline counts')
    seen = set()
    event_indices = set()
    for hand in hands:
        if (not isinstance(hand, dict) or type(hand.get('table_id')) is not int
                or not 1 <= hand['table_id'] <= 4
                or not isinstance(hand.get('hand_id_human_assigned'), str)
                or not hand['hand_id_human_assigned'].strip()
                or not _number(hand.get('first_observed_pts'))
                or not _number(hand.get('last_observed_pts'))
                or not 0 <= hand['first_observed_pts'] <= hand['last_observed_pts']
                or hand.get('human_review_required') is not True
                or not isinstance(hand.get('events'), list) or not hand['events']
                or not isinstance(hand.get('review_flags'), list)):
            raise ValueError('Invalid human-reviewed hand span')
        key = (hand['table_id'], hand['hand_id_human_assigned'])
        if key in seen:
            raise ValueError('Duplicate human-reviewed hand identity')
        seen.add(key)
        if (hand['events'][0].get('timestamp') != hand['first_observed_pts']
                or hand['events'][-1].get('timestamp') != hand['last_observed_pts']):
            raise ValueError('Inconsistent hand span endpoints')
        for event in hand['events']:
            if (not isinstance(event, dict) or not _number(event.get('timestamp'))
                    or not hand['first_observed_pts'] <= event['timestamp'] <= hand['last_observed_pts']
                    or type(event.get('observation_index')) is not int
                    or not 0 <= event['observation_index'] < timeline['counts']['observations']
                    or event['observation_index'] in event_indices
                    or event.get('not_authorized_for_equity_or_ev') is not True):
                raise ValueError('Invalid reviewed event')
            event_indices.add(event['observation_index'])
    for item in timeline['unassigned_observations']:
        if (not isinstance(item, dict) or type(item.get('observation_index')) is not int
                or not 0 <= item['observation_index'] < timeline['counts']['observations']
                or item['observation_index'] in event_indices):
            raise ValueError('Invalid unassigned observation')
        event_indices.add(item['observation_index'])
    if len(event_indices) != timeline['counts']['observations']:
        raise ValueError('Missing or duplicate reviewed observation indices')
    return candidates, hands


def _check_alignment(alignment, queue, timeline):
    if alignment is None:
        return None
    if (not isinstance(alignment, dict) or alignment.get('schema_version') != 1
            or alignment.get('recording_sha256') != queue['recording_sha256']
            or alignment.get('queue_timestamp_semantics') != queue['timestamp_semantics']
            or alignment.get('timeline_timestamp_semantics') != timeline['timestamp_semantics']
            or alignment.get('reviewer_confirmed_same_recording_pts_origin') is not True
            or not _number(alignment.get('queue_pts_minus_timeline_pts_seconds'))
            or abs(alignment['queue_pts_minus_timeline_pts_seconds']) > 3600
            or not isinstance(alignment.get('reviewer_note'), str)
            or not alignment['reviewer_note'].strip()
            or len(alignment['reviewer_note']) > 2000):
        raise ValueError('Invalid explicit reviewer PTS alignment declaration')
    return float(alignment['queue_pts_minus_timeline_pts_seconds'])


def build_visual_timeline_crosswalk(queue, timeline, *, alignment=None,
                                    expected_queue_sha256=None,
                                    expected_timeline_sha256=None):
    """Associate by bounded temporal coincidence only, never assign a hand."""
    candidates, hands = _check_sources(queue, timeline, expected_queue_sha256,
                                       expected_timeline_sha256)
    offset = _check_alignment(alignment, queue, timeline)
    associations = []
    for candidate in candidates:
        start, end = candidate['start_pts_seconds'], candidate['end_pts_seconds']
        matched = []
        if offset is not None:
            for hand in hands:
                if hand['table_id'] != candidate['table_id']:
                    continue
                first = hand['first_observed_pts'] + offset
                last = hand['last_observed_pts'] + offset
                # Endpoint-only touching is not evidence of a temporal interval.
                if min(end, last) <= max(start, first):
                    continue
                events = [e['observation_index'] for e in hand['events']
                          if start <= e['timestamp'] + offset <= end]
                matched.append({
                    'hand_id_human_assigned_not_verified': hand['hand_id_human_assigned'],
                    'first_observed_pts_in_queue_clock': first,
                    'last_observed_pts_in_queue_clock': last,
                    'observed_event_indices_within_candidate': events,
                    'hand_review_flags': list(hand.get('review_flags', [])),
                    'association_confidence': 'not_calibrated',
                })
        status = ('pts_alignment_not_declared' if offset is None else
                  'no_observed_hand_span_overlap' if not matched else
                  'single_temporal_overlap_unverified' if len(matched) == 1 else
                  'ambiguous_multiple_hands_overlap_unverified')
        associations.append({
            'pixel_review_rank': candidate['pixel_review_rank'],
            'table_id': candidate['table_id'],
            'region_label_hypothesis': candidate['region_label_hypothesis'],
            'candidate_interval_queue_pts': [start, end],
            'first_frame': candidate.get('first_frame'),
            'last_frame': candidate.get('last_frame'),
            'status': status,
            'possible_human_assigned_hands': matched,
            'hand_assigned_automatically': False,
            'poker_event_recognized': False,
            'requires_manual_review': True,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'review_only_roi_to_human_timeline_temporal_crosswalk',
        'recording_sha256': queue['recording_sha256'],
        'source_roi_queue_sha256': canonical_sha256(queue),
        'source_reviewed_timeline_sha256': canonical_sha256(timeline),
        'source_pts_alignment_declaration_sha256': (canonical_sha256(alignment)
                                                     if alignment is not None else None),
        'pts_alignment_declared_by_reviewer_not_independently_verified': offset is not None,
        'queue_pts_minus_timeline_pts_seconds': offset,
        'associations': associations,
        'counts': {
            'roi_candidates': len(associations),
            'without_alignment': sum(x['status'] == 'pts_alignment_not_declared' for x in associations),
            'single_overlap_unverified': sum(x['status'] == 'single_temporal_overlap_unverified' for x in associations),
            'ambiguous_overlap_unverified': sum(x['status'] == 'ambiguous_multiple_hands_overlap_unverified' for x in associations),
            'without_observed_overlap': sum(x['status'] == 'no_observed_hand_span_overlap' for x in associations),
        },
        'requires_manual_review': True,
        'ready_for_equity_or_ev': False,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Time alignment is a human declaration, not measured synchronization. '
                    'Pixel changes are not OCR facts, card events, betting actions, '
                    'hand boundaries, clip permissions, or evidence of strategic errors.'),
    }


def export_visual_timeline_crosswalk(queue_json, timeline_json, output_json, *,
                                     alignment_json=None, **kwargs):
    src1, src2, dest = map(Path, (queue_json, timeline_json, output_json))
    align_path = Path(alignment_json) if alignment_json is not None else None
    sources = [src1, src2] + ([align_path] if align_path is not None else [])
    if (any(p.is_symlink() or not p.is_file() for p in sources)
            or dest.is_symlink() or dest.exists()
            or any(dest.resolve() == p.resolve() for p in sources)):
        raise ValueError('Require regular JSON inputs and a new output path')
    queue, timeline = [json.loads(p.read_text(encoding='utf-8')) for p in (src1, src2)]
    alignment = json.loads(align_path.read_text(encoding='utf-8')) if align_path else None
    result = build_visual_timeline_crosswalk(queue, timeline, alignment=alignment, **kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roi_review_queue_json')
    parser.add_argument('human_reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--alignment-json', help='Optional, explicit human-reviewed PTS alignment')
    parser.add_argument('--expected-queue-sha256')
    parser.add_argument('--expected-timeline-sha256')
    args = parser.parse_args()
    result = export_visual_timeline_crosswalk(
        args.roi_review_queue_json, args.human_reviewed_timeline_json, args.output_json,
        alignment_json=args.alignment_json,
        expected_queue_sha256=args.expected_queue_sha256,
        expected_timeline_sha256=args.expected_timeline_sha256)
    print(json.dumps(result['counts']))
