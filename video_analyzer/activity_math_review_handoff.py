"""Produce an offline, *unapproved* reviewer worksheet from math-readiness triage.

The source triage is independently recomputed from the exact hand packet and
human-reviewed timeline. Preview intervals are navigation hints within observed
PTS only; they are NOT hand boundaries or permission to export/rank clips.
No ranges, pot odds, equity, EV or hidden cards are inferred.
"""
import argparse
import json
import math
from pathlib import Path

from activity_math_readiness_triage import build_math_readiness_triage
from activity_snapshot_chain import canonical_sha256

STATUS = 'human_math_review_worksheet_unverified_no_auto_clips'


def _window(pts, first, last, before, after):
    # Observed PTS limits are NOT actual hand boundaries.
    return [max(first, pts - before), min(last, pts + after)]


def build_math_review_handoff(triage, packet, timeline, *,
                              expected_triage_sha256=None,
                              expected_packet_sha256=None,
                              expected_timeline_sha256=None,
                              seconds_before=5, seconds_after=5):
    """Bind every decision review row to a validated, same-hand source event."""
    for label, value in [('seconds_before', seconds_before), ('seconds_after', seconds_after)]:
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 30:
            raise ValueError('Invalid ' + label)
    if not isinstance(triage, dict) or not isinstance(packet, dict) or not isinstance(timeline, dict):
        raise ValueError('Expected JSON objects')
    triage_hash = canonical_sha256(triage)
    if expected_triage_sha256 is not None and triage_hash != expected_triage_sha256:
        raise ValueError('Triage SHA-256 mismatch')
    count = triage.get('counts', {}).get('tasks_returned')
    if type(count) is not int or not 0 <= count <= 5000:
        raise ValueError('Invalid triage task count')
    expected = build_math_readiness_triage(
        packet, timeline, expected_packet_sha256=expected_packet_sha256,
        expected_timeline_sha256=expected_timeline_sha256,
        max_tasks=max(1, count))
    # Compare the complete result: do not trust attacker-supplied task PTS,
    # blockers, identity, ordering, flags, or math/clip authorization bits.
    if triage != expected:
        raise ValueError('Triage does not match recomputed source evidence')
    hands = {(h['table_id'], h['hand_id_human_assigned']): h
             for h in timeline['hands']}
    rows = []
    for task in expected['tasks']:
        key = (task['table_id'], task['hand_id_human_assigned_not_verified'])
        hand = hands[key]
        matches = [e for e in hand['events']
                   if e['observation_index'] == task['observation_index']]
        if len(matches) != 1 or matches[0]['timestamp'] != task['decision_pts_seconds']:
            raise ValueError('Decision PTS and source event mismatch')
        pts = task['decision_pts_seconds']
        first, last = hand['first_observed_pts'], hand['last_observed_pts']
        if not first <= pts <= last:
            raise ValueError('Decision outside observed hand timestamps')
        rows.append({
            'table_id': key[0],
            'hand_id_human_assigned_not_verified': key[1],
            'observation_index': task['observation_index'],
            'decision_pts_seconds': pts,
            'action_human_annotated_not_verified': task['action_human_annotated_not_verified'],
            'review_interval_observed_pts_not_hand_boundaries': _window(
                pts, first, last, seconds_before, seconds_after),
            'source_event_sha256': canonical_sha256(matches[0]),
            'same_pts_field_status': task['same_pts_field_status'],
            'review_blockers': task['review_blockers'],
            'human_review_fields_to_complete': {
                'hero_cards': None, 'board': None, 'pot_before_action': None,
                'call_or_raise_amount': None, 'hero_actor_confirmed': None,
                'opponent_count': None, 'effective_stacks': None,
                'rake_assumption': None, 'opponent_range_assumption': None,
                'fold_probability_assumption': None,
                'future_betting_assumption': None, 'independent_frame_audit': None,
                'reviewer_notes': None,
            },
            'reviewer_approved_for_manual_clip': False,
            'model_inputs_extracted': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
        })
    return {
        'schema_version': 1,
        'analysis_status': STATUS,
        'recording_sha256': timeline['recording_sha256'],
        'timestamp_semantics': timeline['timestamp_semantics'],
        'source_triage_sha256': triage_hash,
        'source_hand_review_packet_sha256': canonical_sha256(packet),
        'source_reviewed_timeline_sha256': canonical_sha256(timeline),
        'preview_window_seconds': {'before': seconds_before, 'after': seconds_after},
        'review_tasks': rows,
        'counts': {'review_tasks': len(rows),
                   'omitted_due_to_upstream_budget': expected['counts']['tasks_omitted_by_budget']},
        'requires_manual_review': True,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Navigation windows use only observed timestamps and are not hand boundaries. '
                    'Human annotations, OCR, actions and model ranges are unverified. '
                    'No automatic clips, strategic ranking, equity or EV authorized.'),
    }


def export_math_review_handoff(triage_json, packet_json, timeline_json, output_json, **kwargs):
    sources = [Path(p) for p in (triage_json, packet_json, timeline_json)]
    output = Path(output_json)
    if (any(p.is_symlink() or not p.is_file() for p in sources)
            or output.exists() or output.is_symlink()
            or output.resolve() in {p.resolve() for p in sources}):
        raise ValueError('Require regular input JSON files and new distinct output')
    triage, packet, timeline = [json.loads(p.read_text(encoding='utf-8')) for p in sources]
    result = build_math_review_handoff(triage, packet, timeline, **kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as target:
        json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('math_triage_json', 'hand_review_packet_json', 'reviewed_timeline_json', 'output_json'):
        parser.add_argument(field)
    parser.add_argument('--expected-triage-sha256')
    parser.add_argument('--expected-packet-sha256')
    parser.add_argument('--expected-timeline-sha256')
    parser.add_argument('--seconds-before', type=float, default=5)
    parser.add_argument('--seconds-after', type=float, default=5)
    args = parser.parse_args(argv)
    report = export_math_review_handoff(
        args.math_triage_json, args.hand_review_packet_json, args.reviewed_timeline_json,
        args.output_json, expected_triage_sha256=args.expected_triage_sha256,
        expected_packet_sha256=args.expected_packet_sha256,
        expected_timeline_sha256=args.expected_timeline_sha256,
        seconds_before=args.seconds_before, seconds_after=args.seconds_after)
    print(json.dumps(report['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
