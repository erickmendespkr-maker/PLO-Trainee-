"""Offline, review-only packets joining timeline audit, ROI frames and optional OCR.

All joins depend on explicit reviewer clock declarations and pre-existing human
hand IDs. This module never authenticates pixels, cards, actions or math inputs.
"""
import argparse
import json
from pathlib import Path

from activity_consistency_frame_review import build_consistency_frame_review
from activity_ocr_timeline_review import build_ocr_timeline_review
from activity_snapshot_chain import canonical_sha256


def _budget(value, name):
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError(f'Invalid {name} budget')


def build_hand_review_packet(queue, timeline, *, queue_alignment=None,
                             ocr=None, ocr_alignment=None,
                             expected_queue_sha256=None,
                             expected_timeline_sha256=None,
                             expected_ocr_sha256=None,
                             max_frames_per_flag=5, max_ocr_per_hand=20,
                             max_unassigned_ocr=100):
    """Build bounded per-hand manual review tasks without granting poker authority."""
    _budget(max_frames_per_flag, 'frame')
    if max_frames_per_flag > 20:
        raise ValueError('Frame budget exceeds upstream limit')
    _budget(max_ocr_per_hand, 'per-hand OCR')
    _budget(max_unassigned_ocr, 'unassigned OCR')
    if ocr is None and (ocr_alignment is not None or expected_ocr_sha256 is not None):
        raise ValueError('OCR alignment/digest supplied without OCR report')

    frame = build_consistency_frame_review(
        queue, timeline, alignment=queue_alignment,
        expected_queue_sha256=expected_queue_sha256,
        expected_timeline_sha256=expected_timeline_sha256,
        max_frames_per_flag=max_frames_per_flag)
    ocr_review = None
    if ocr is not None:
        ocr_review = build_ocr_timeline_review(
            ocr, timeline, alignment=ocr_alignment,
            expected_ocr_sha256=expected_ocr_sha256,
            expected_timeline_sha256=expected_timeline_sha256)
        if ocr_review['recording_sha256'] != frame['recording_sha256']:
            raise ValueError('OCR and ROI queue refer to different recordings')

    packets = {}
    for hand in timeline['hands']:
        key = (hand['table_id'], hand['hand_id_human_assigned'])
        packets[key] = {
            'table_id': key[0],
            'hand_id_human_assigned_not_verified': key[1],
            'observed_timeline_pts': [hand['first_observed_pts'], hand['last_observed_pts']],
            'observation_indices': [e['observation_index'] for e in hand['events']],
            'existing_human_review_flags': list(hand['review_flags']),
            'consistency_flags_with_frame_suggestions': [],
            'ocr_exact_pts_review_candidates': [],
            'omitted_ocr_due_to_budget': 0,
            'requires_manual_review': True,
            'ready_for_equity_or_ev': False,
            'hand_reconstruction_verified': False,
        }
    for flag in frame['flags']:
        key = (flag['table_id'], flag['hand_id_human_assigned_not_verified'])
        # The upstream audit already validates this identity against the timeline.
        packets[key]['consistency_flags_with_frame_suggestions'].append(flag)

    unassigned = []
    assigned_count = 0
    if ocr_review is not None:
        for candidate in ocr_review['candidates']:
            matches = candidate['possible_human_assigned_hands_not_verified']
            key = ((candidate['table_id'], matches[0]['hand_id'])
                   if len(matches) == 1 else None)
            # A candidate must have a single exact reviewed field, not merely a
            # time overlap, and must be backed by explicit reviewer alignment.
            eligible = (key in packets and ocr_review['pts_alignment_declared_not_verified']
                        and candidate['status'] in (
                            'ocr_candidate_agrees_with_reviewed_label_not_verified',
                            'ocr_candidate_disagrees_with_reviewed_label_not_verified',
                            'ocr_unparseable_manual_review'))
            entry = {
                'candidate_index': candidate['candidate_index'],
                'table_id': candidate['table_id'],
                'ocr_pts_seconds': candidate['ocr_pts_seconds'],
                'field': candidate['field'],
                'source_image_not_reaudited': candidate['source_image'],
                'source_sha256_not_reaudited': candidate['source_sha256'],
                'status': candidate['status'],
                'same_pts_conflicting_ocr_candidates':
                    candidate['same_pts_conflicting_ocr_candidates'],
                'engine_confidence_not_calibrated':
                    candidate['ocr_engine_confidence_uncalibrated'],
                'poker_event_recognized': False,
            }
            if eligible:
                target = packets[key]['ocr_exact_pts_review_candidates']
                assigned_count += 1
                if len(target) < max_ocr_per_hand:
                    target.append(entry)
                else:
                    packets[key]['omitted_ocr_due_to_budget'] += 1
            else:
                unassigned.append(entry)

    hands = [packets[k] for k in sorted(packets, key=lambda k:
             (k[0], packets[k]['observed_timeline_pts'][0], k[1]))]
    return {
        'schema_version': 1,
        'analysis_status': 'manual_review_packets_unverified_no_math_authority',
        'recording_sha256': frame['recording_sha256'],
        'source_roi_queue_sha256': canonical_sha256(queue),
        'source_reviewed_timeline_sha256': canonical_sha256(timeline),
        'source_ocr_report_sha256': canonical_sha256(ocr) if ocr is not None else None,
        'source_frame_review_sha256': canonical_sha256(frame),
        'source_ocr_timeline_review_sha256': (
            canonical_sha256(ocr_review) if ocr_review is not None else None),
        'queue_alignment_sha256': (
            canonical_sha256(queue_alignment) if queue_alignment is not None else None),
        'ocr_alignment_sha256': (
            canonical_sha256(ocr_alignment) if ocr_alignment is not None else None),
        'hands': hands,
        'unassigned_ocr_candidates': unassigned[:max_unassigned_ocr],
        'counts': {
            'hands': len(hands),
            'consistency_flags': len(frame['flags']),
            'frame_suggestions': frame['counts']['suggested_roi_intervals'],
            'ocr_candidates_total': len(ocr_review['candidates']) if ocr_review else 0,
            'ocr_candidates_exact_pts_unique_hand': assigned_count,
            'ocr_candidates_unassigned': len(unassigned),
            'ocr_candidates_unassigned_omitted': max(0, len(unassigned)-max_unassigned_ocr),
            'ocr_candidates_assigned_omitted': sum(
                h['omitted_ocr_due_to_budget'] for h in hands),
        },
        'requires_manual_review': True,
        'ready_for_equity_or_ev': False,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Human hand IDs and reviewer clock alignments are not independently verified. '
                    'ROI changes and OCR are review hints, not confirmed cards, actions, '
                    'hand boundaries, ranges, equity, EV, or poker errors.'),
    }


def export_hand_review_packet(queue_json, timeline_json, output_json, *,
                              queue_alignment_json=None, ocr_json=None,
                              ocr_alignment_json=None, **kwargs):
    inputs = [Path(queue_json), Path(timeline_json)]
    extras = [queue_alignment_json, ocr_json, ocr_alignment_json]
    inputs.extend(Path(p) for p in extras if p is not None)
    destination = Path(output_json)
    if (any(p.is_symlink() or not p.is_file() for p in inputs)
            or destination.is_symlink() or destination.exists()
            or any(destination.resolve() == p.resolve() for p in inputs)):
        raise ValueError('Require regular JSON inputs and a new distinct output')
    data = {str(p): json.loads(p.read_text(encoding='utf-8')) for p in inputs}
    result = build_hand_review_packet(
        data[str(inputs[0])], data[str(inputs[1])],
        queue_alignment=data[str(Path(queue_alignment_json))]
            if queue_alignment_json is not None else None,
        ocr=data[str(Path(ocr_json))] if ocr_json is not None else None,
        ocr_alignment=data[str(Path(ocr_alignment_json))]
            if ocr_alignment_json is not None else None,
        **kwargs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roi_queue_json')
    parser.add_argument('reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--queue-alignment-json')
    parser.add_argument('--ocr-json')
    parser.add_argument('--ocr-alignment-json')
    parser.add_argument('--expected-queue-sha256')
    parser.add_argument('--expected-timeline-sha256')
    parser.add_argument('--expected-ocr-sha256')
    parser.add_argument('--max-frames-per-flag', type=int, default=5)
    parser.add_argument('--max-ocr-per-hand', type=int, default=20)
    parser.add_argument('--max-unassigned-ocr', type=int, default=100)
    args = parser.parse_args()
    result = export_hand_review_packet(
        args.roi_queue_json, args.reviewed_timeline_json, args.output_json,
        queue_alignment_json=args.queue_alignment_json,
        ocr_json=args.ocr_json, ocr_alignment_json=args.ocr_alignment_json,
        expected_queue_sha256=args.expected_queue_sha256,
        expected_timeline_sha256=args.expected_timeline_sha256,
        expected_ocr_sha256=args.expected_ocr_sha256,
        max_frames_per_flag=args.max_frames_per_flag,
        max_ocr_per_hand=args.max_ocr_per_hand,
        max_unassigned_ocr=args.max_unassigned_ocr)
    print(json.dumps(result['counts'], sort_keys=True))
