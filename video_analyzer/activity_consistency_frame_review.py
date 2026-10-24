"""Build a conservative, offline frame-review plan for timeline consistency flags.

Joins human-reviewed timeline audit flags to *uncalibrated* ROI pixel hints.
Only a reviewer-supplied PTS alignment permits temporal suggestions. A suggested
frame is not evidence of a card, action, hand boundary, EV, or poker mistake.
"""
import argparse
import json
import math
from pathlib import Path

from activity_snapshot_chain import canonical_sha256
from activity_timeline_consistency_audit import build_timeline_consistency_audit
from activity_visual_timeline_crosswalk import build_visual_timeline_crosswalk

_FIELD_TO_ROI = {'board': 'board', 'hero_cards': 'hero_cards', 'pot': 'pot'}


def build_consistency_frame_review(queue, timeline, *, alignment=None,
                                   expected_queue_sha256=None,
                                   expected_timeline_sha256=None,
                                   max_frames_per_flag=5):
    """Suggest same-hand, same-ROI frames near an audit flag, never verify it.

    Only crosswalk entries with exactly one temporal hand overlap are eligible.
    For a changed observation, compare the interval between prior/current PTS;
    for a single observation, compare its timestamp. No future values are copied.
    """
    if type(max_frames_per_flag) is not int or not 1 <= max_frames_per_flag <= 20:
        raise ValueError('Invalid review frame budget')
    crosswalk = build_visual_timeline_crosswalk(
        queue, timeline, alignment=alignment,
        expected_queue_sha256=expected_queue_sha256,
        expected_timeline_sha256=expected_timeline_sha256)
    audit = build_timeline_consistency_audit(
        timeline, expected_timeline_sha256=expected_timeline_sha256)
    # Preserve one-to-one hand identity. Ambiguous crosswalk entries never match.
    by_hand = {}
    if crosswalk['pts_alignment_declared_by_reviewer_not_independently_verified']:
        for entry in crosswalk['associations']:
            if entry['status'] != 'single_temporal_overlap_unverified':
                continue
            hand = entry['possible_human_assigned_hands'][0]
            key = (entry['table_id'], hand['hand_id_human_assigned_not_verified'])
            by_hand.setdefault(key, []).append(entry)
    offset = crosswalk['queue_pts_minus_timeline_pts_seconds']
    rows = []
    for hand in audit['hands']:
        key = (hand['table_id'], hand['hand_id_human_assigned'])
        for flag in hand['audit_flags']:
            label = _FIELD_TO_ROI.get(flag['field'])
            current = flag['pts_seconds']
            prior = flag['prior_pts_seconds']
            start = min(current, prior) if prior is not None else current
            end = max(current, prior) if prior is not None else current
            candidates = []
            if offset is not None and label is not None:
                for entry in by_hand.get(key, []):
                    if entry['region_label_hypothesis'] != label:
                        continue
                    left, right = entry['candidate_interval_queue_pts']
                    # Closed overlap includes a single flagged observation.
                    if right < start + offset or left > end + offset:
                        continue
                    candidates.append({
                        'pixel_review_rank': entry['pixel_review_rank'],
                        'region_label_hypothesis': label,
                        'candidate_interval_queue_pts': [left, right],
                        'first_frame': entry['first_frame'],
                        'last_frame': entry['last_frame'],
                        'association_confidence': 'not_calibrated',
                        'poker_event_recognized': False,
                    })
            candidates.sort(key=lambda c: c['pixel_review_rank'])
            status = ('pts_alignment_not_declared' if offset is None else
                      'no_roi_for_audit_field' if label is None else
                      'candidate_frames_for_manual_review' if candidates else
                      'no_unambiguous_same_hand_roi_overlap')
            rows.append({
                'table_id': hand['table_id'],
                'hand_id_human_assigned_not_verified': hand['hand_id_human_assigned'],
                'audit_kind': flag['kind'], 'field': flag['field'],
                'observation_index': flag['observation_index'],
                'prior_observation_index': flag['prior_observation_index'],
                'flag_interval_timeline_pts': [start, end],
                'source_image_not_reaudited': flag['source_image_not_reaudited'],
                'status': status,
                'total_matching_roi_candidates': len(candidates),
                'omitted_due_to_per_flag_budget': max(0, len(candidates) - max_frames_per_flag),
                'suggested_roi_frames': candidates[:max_frames_per_flag],
                'requires_manual_review': True,
                'strategic_error_established': False,
            })
    return {
        'schema_version': 1,
        'analysis_status': 'review_only_consistency_flag_frame_suggestions',
        'recording_sha256': timeline['recording_sha256'],
        'source_roi_queue_sha256': canonical_sha256(queue),
        'source_reviewed_timeline_sha256': canonical_sha256(timeline),
        'source_consistency_audit_sha256': canonical_sha256(audit),
        'source_visual_crosswalk_sha256': canonical_sha256(crosswalk),
        'source_pts_alignment_declaration_sha256': (
            canonical_sha256(alignment) if alignment is not None else None),
        'pts_alignment_declared_by_reviewer_not_independently_verified': offset is not None,
        'queue_pts_minus_timeline_pts_seconds': offset,
        'max_frames_per_flag': max_frames_per_flag,
        'flags': rows,
        'counts': {
            'audit_flags': len(rows),
            'flags_with_suggested_roi_frames': sum(bool(r['suggested_roi_frames']) for r in rows),
            'flags_without_suggested_roi_frames': sum(not r['suggested_roi_frames'] for r in rows),
            'suggested_roi_intervals': sum(len(r['suggested_roi_frames']) for r in rows),
        },
        'requires_manual_review': True,
        'ready_for_equity_or_ev': False,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Only pixel-change frame suggestions. Reviewer alignment and human hand IDs '
                    'are not independently verified. No cards, actions, hand boundaries, '
                    'clips, ranges, equity, EV or mistakes are inferred.'),
    }


def export_consistency_frame_review(queue_json, timeline_json, output_json, *,
                                    alignment_json=None, **kwargs):
    src1, src2, dest = map(Path, (queue_json, timeline_json, output_json))
    align = Path(alignment_json) if alignment_json is not None else None
    sources = [src1, src2] + ([align] if align is not None else [])
    if (any(p.is_symlink() or not p.is_file() for p in sources)
            or dest.is_symlink() or dest.exists()
            or any(dest.resolve() == p.resolve() for p in sources)):
        raise ValueError('Require regular JSON inputs and a new distinct output')
    q, t = [json.loads(p.read_text(encoding='utf-8')) for p in (src1, src2)]
    a = json.loads(align.read_text(encoding='utf-8')) if align is not None else None
    result = build_consistency_frame_review(q, t, alignment=a, **kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roi_review_queue_json')
    parser.add_argument('human_reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--alignment-json')
    parser.add_argument('--expected-queue-sha256')
    parser.add_argument('--expected-timeline-sha256')
    parser.add_argument('--max-frames-per-flag', type=int, default=5)
    args = parser.parse_args()
    result = export_consistency_frame_review(
        args.roi_review_queue_json, args.human_reviewed_timeline_json, args.output_json,
        alignment_json=args.alignment_json,
        expected_queue_sha256=args.expected_queue_sha256,
        expected_timeline_sha256=args.expected_timeline_sha256,
        max_frames_per_flag=args.max_frames_per_flag)
    print(json.dumps(result['counts'], sort_keys=True))
