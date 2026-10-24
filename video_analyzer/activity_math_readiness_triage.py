"""Offline, fail-closed review checklist for possible PLO5/PLO6 decisions.

Consumes human-assigned hand packets and their exact source timeline. It never
copies observations from later timestamps, infers a preflop board, authenticates
OCR, computes equity/EV, or approves a decision for automated clip ranking.
"""
import argparse
import json
import math
from pathlib import Path

from activity_snapshot_chain import canonical_sha256
from activity_timeline_consistency_audit import _validate, build_timeline_consistency_audit

DECISIONS = frozenset(('fold', 'check', 'call', 'bet', 'raise'))
FIELD_MAP = {'hero_cards': 'hero_cards_visible', 'board': 'board_visible',
             'pot': 'pot_observed', 'amount': 'amount_observed',
             'variant': 'variant_human_annotated', 'actor': 'actor_human_annotated'}
OCR_FIELDS = frozenset(('hero_cards', 'board', 'pot', 'amount'))


def _packet_map(packet, timeline):
    if (not isinstance(packet, dict) or packet.get('schema_version') != 1
            or packet.get('analysis_status') != 'manual_review_packets_unverified_no_math_authority'
            or packet.get('recording_sha256') != timeline['recording_sha256']
            or packet.get('source_reviewed_timeline_sha256') != canonical_sha256(timeline)
            or any(packet.get(key) is not False for key in
                   ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
                    'automatic_clip_selection_authorized', 'strategic_error_established'))
            or packet.get('requires_manual_review') is not True):
        raise ValueError('Packet/timeline identity or unverified status mismatch')
    entries = packet.get('hands')
    if not isinstance(entries, list) or len(entries) != len(timeline['hands']):
        raise ValueError('Packet hand count mismatch')
    expected_audit = build_timeline_consistency_audit(timeline)
    audit_by_key = {(h['table_id'], h['hand_id_human_assigned']): h
                    for h in expected_audit['hands']}
    mapped = {}
    for hand in entries:
        if not isinstance(hand, dict):
            raise ValueError('Invalid packet hand')
        key = (hand.get('table_id'), hand.get('hand_id_human_assigned_not_verified'))
        if key not in audit_by_key or key in mapped:
            raise ValueError('Unexpected/duplicate packet hand')
        if (hand.get('ready_for_equity_or_ev') is not False
                or hand.get('hand_reconstruction_verified') is not False
                or hand.get('requires_manual_review') is not True):
            raise ValueError('Packet cannot promote hand authority')
        source = next(h for h in timeline['hands']
                      if (h['table_id'], h['hand_id_human_assigned']) == key)
        if (hand.get('observed_timeline_pts') != [source['first_observed_pts'],
                                                  source['last_observed_pts']]
                or hand.get('observation_indices') != [e['observation_index'] for e in source['events']]
                or hand.get('existing_human_review_flags') != source['review_flags']):
            raise ValueError('Packet observations disagree with timeline')
        flags = hand.get('consistency_flags_with_frame_suggestions')
        if not isinstance(flags, list):
            raise ValueError('Invalid packet consistency flags')
        expected_flags = sorted((f['kind'], f['observation_index'], f['prior_observation_index'])
                                for f in audit_by_key[key]['audit_flags'])
        actual_flags = []
        for f in flags:
            if not isinstance(f, dict) or f.get('strategic_error_established') is not False:
                raise ValueError('Invalid packet consistency flag')
            actual_flags.append((f.get('audit_kind'), f.get('observation_index'),
                                 f.get('prior_observation_index')))
        if sorted(actual_flags) != expected_flags:
            raise ValueError('Packet audit flags disagree with timeline')
        ocr = hand.get('ocr_exact_pts_review_candidates')
        if (not isinstance(ocr, list) or type(hand.get('omitted_ocr_due_to_budget')) is not int
                or hand['omitted_ocr_due_to_budget'] < 0):
            raise ValueError('Invalid packet OCR candidates')
        for candidate in ocr:
            if (not isinstance(candidate, dict) or candidate.get('poker_event_recognized') is not False
                    or type(candidate.get('candidate_index')) is not int
                    or candidate['candidate_index'] < 0
                    or candidate.get('table_id') != key[0]
                    or type(candidate.get('ocr_pts_seconds')) not in (int, float)
                    or not math.isfinite(candidate['ocr_pts_seconds'])):
                raise ValueError('Invalid unverified OCR candidate')
        mapped[key] = hand
    return mapped


def _same_frame_field(event, field):
    """Presence is a review hint only; no temporal forward-fill or authentication."""
    value = event.get(FIELD_MAP[field])
    if value is None:
        return 'missing_at_decision_pts'
    if field not in OCR_FIELDS:
        return 'human_annotation_not_independently_verified'
    evidence = event.get('field_evidence', {}).get('bet' if field == 'amount' else field)
    if not isinstance(evidence, dict):
        return 'human_label_without_same_pts_ocr_reference'
    pts = evidence.get('decoded_source_pts')
    if (type(pts) not in (int, float) or not math.isfinite(pts)
            or pts != event['timestamp']):
        return 'ocr_reference_pts_mismatch_manual_review'
    return 'human_label_with_same_pts_ocr_reference_not_verified'


def build_math_readiness_triage(packet, timeline, *, expected_packet_sha256=None,
                                expected_timeline_sha256=None, max_tasks=1000):
    """List missing evidence/model assumptions; all tasks remain blocked for math."""
    if type(max_tasks) is not int or not 1 <= max_tasks <= 5000:
        raise ValueError('Invalid task budget')
    hands = _validate(timeline, expected_timeline_sha256)
    packet_digest = canonical_sha256(packet)
    if expected_packet_sha256 is not None and packet_digest != expected_packet_sha256:
        raise ValueError('Packet SHA-256 mismatch')
    by_key = _packet_map(packet, timeline)
    tasks = []
    total = 0
    for hand in hands:
        key = (hand['table_id'], hand['hand_id_human_assigned'])
        review = by_key[key]
        for event in hand['events']:
            action = event.get('action_human_annotated_not_ocr_verified')
            if action not in DECISIONS:
                continue
            total += 1
            if len(tasks) >= max_tasks:
                continue
            statuses = {field: _same_frame_field(event, field) for field in FIELD_MAP}
            variant = event.get('variant_human_annotated')
            hero = event.get('hero_cards_visible')
            if (variant in ('PLO5', 'PLO6') and hero is not None
                    and len(hero) != int(variant[-1])):
                statuses['hero_cards'] = 'hero_card_count_conflicts_with_variant'
            blockers = ['independent_video_content_validation_required',
                        'hero_actor_identity_not_verified',
                        'opponent_ranges_and_player_count_not_supplied',
                        'effective_stacks_rake_future_betting_model_not_supplied',
                        'action_semantics_and_bet_amount_not_independently_verified']
            blockers.extend('missing_same_pts_' + field for field, state in statuses.items()
                            if state == 'missing_at_decision_pts')
            blockers.extend('review_' + field + '_provenance' for field, state in statuses.items()
                            if state in ('human_label_without_same_pts_ocr_reference',
                                         'ocr_reference_pts_mismatch_manual_review'))
            if statuses['hero_cards'] == 'hero_card_count_conflicts_with_variant':
                blockers.append('hero_card_count_variant_mismatch')
            if hand['review_flags'] or review['consistency_flags_with_frame_suggestions']:
                blockers.append('hand_timeline_consistency_requires_review')
            if any(c.get('same_pts_conflicting_ocr_candidates') is True
                   for c in review['ocr_exact_pts_review_candidates']):
                blockers.append('conflicting_ocr_candidates_require_review')
            if review['omitted_ocr_due_to_budget']:
                blockers.append('ocr_review_budget_truncated')
            if action in ('bet', 'raise'):
                blockers.append('raise_size_fold_equity_and_response_model_not_supplied')
            tasks.append({
                'table_id': key[0], 'hand_id_human_assigned_not_verified': key[1],
                'observation_index': event['observation_index'],
                'decision_pts_seconds': event['timestamp'],
                'action_human_annotated_not_verified': action,
                'same_pts_field_status': statuses,
                'ocr_candidates_in_hand_not_event_verified': len(review['ocr_exact_pts_review_candidates']),
                'review_blockers': sorted(set(blockers)),
                'model_inputs_extracted': False,
                'ready_for_equity_or_ev': False,
                'decision_quality_established': False,
                'clip_selection_authorized': False,
            })
    return {
        'schema_version': 1,
        'analysis_status': 'math_input_review_triage_no_calculation_no_authority',
        'recording_sha256': timeline['recording_sha256'],
        'source_reviewed_timeline_sha256': canonical_sha256(timeline),
        'source_hand_review_packet_sha256': packet_digest,
        'timestamp_semantics': timeline['timestamp_semantics'],
        'tasks': tasks,
        'counts': {'hands': len(hands), 'decision_observations_total': total,
                   'tasks_returned': len(tasks), 'tasks_omitted_by_budget': total-len(tasks),
                   'tasks_ready_for_math': 0},
        'requires_manual_review': True,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Presence of a human label or OCR reference is not video verification. '
                    'Never borrow future observations. No ranges, equity, EV, poker errors '
                    'or automatic clip selection are inferred or authorized.'),
    }


def export_math_readiness_triage(packet_json, timeline_json, output_json, **kwargs):
    sources = [Path(packet_json), Path(timeline_json)]
    target = Path(output_json)
    if (any(not p.is_file() or p.is_symlink() for p in sources)
            or target.exists() or target.is_symlink()
            or any(target.resolve() == p.resolve() for p in sources)):
        raise ValueError('Require regular JSON inputs and a new distinct output')
    packet, timeline = [json.loads(p.read_text(encoding='utf-8')) for p in sources]
    result = build_math_readiness_triage(packet, timeline, **kwargs)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hand_review_packet_json')
    parser.add_argument('reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--expected-packet-sha256')
    parser.add_argument('--expected-timeline-sha256')
    parser.add_argument('--max-tasks', type=int, default=1000)
    args = parser.parse_args()
    result = export_math_readiness_triage(
        args.hand_review_packet_json, args.reviewed_timeline_json, args.output_json,
        expected_packet_sha256=args.expected_packet_sha256,
        expected_timeline_sha256=args.expected_timeline_sha256,
        max_tasks=args.max_tasks)
    print(json.dumps(result['counts'], sort_keys=True))
