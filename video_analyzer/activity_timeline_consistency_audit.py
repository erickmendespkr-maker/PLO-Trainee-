"""Offline consistency audit of *human-reviewed* PLO5/PLO6 timelines.

Produces review flags, not verified poker facts or strategic advice. Missing
observations are never filled with future board/hero/pot values. Pot decreases
are review hints only (payouts, side pots and UI resets are possible).
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')
_BLOCKED = ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
            'automatic_clip_selection_authorized', 'strategic_error_established')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _cards(value, lengths):
    return (value is None or (isinstance(value, list) and len(value) in lengths
            and all(isinstance(c, str) and _CARD.fullmatch(c) for c in value)
            and len(set(value)) == len(value)))


def _validate(timeline, expected_sha256):
    if (not isinstance(timeline, dict) or timeline.get('schema_version') != 1
            or timeline.get('analysis_status') !=
            'human_reviewed_visible_timeline_not_verified_hand_reconstruction'
            or not isinstance(timeline.get('recording_sha256'), str)
            or not _SHA.fullmatch(timeline['recording_sha256'])
            or not isinstance(timeline.get('source_review_sha256'), str)
            or not _SHA.fullmatch(timeline['source_review_sha256'])
            or not isinstance(timeline.get('timestamp_semantics'), str)
            or 'decoded' not in timeline['timestamp_semantics']
            or any(timeline.get(flag) is not False for flag in _BLOCKED)):
        raise ValueError('Invalid reviewed timeline status or provenance')
    if expected_sha256 is not None and (
            not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256)
            or canonical_sha256(timeline) != expected_sha256):
        raise ValueError('Timeline SHA-256 mismatch')
    hands, counts = timeline.get('hands'), timeline.get('counts')
    if (not isinstance(hands, list) or len(hands) > 10000
            or not isinstance(counts, dict)
            or type(counts.get('hands_human_assigned')) is not int
            or counts['hands_human_assigned'] != len(hands)):
        raise ValueError('Invalid timeline hand counts')
    identities = set()
    for hand in hands:
        if (not isinstance(hand, dict) or type(hand.get('table_id')) is not int
                or not 1 <= hand['table_id'] <= 4
                or not isinstance(hand.get('hand_id_human_assigned'), str)
                or not hand['hand_id_human_assigned']
                or hand.get('human_review_required') is not True
                or not isinstance(hand.get('review_flags'), list)
                or not isinstance(hand.get('events'), list) or not hand['events']
                or len(hand['events']) > 10000
                or not _number(hand.get('first_observed_pts'))
                or not _number(hand.get('last_observed_pts'))
                or hand['last_observed_pts'] < hand['first_observed_pts']):
            raise ValueError('Invalid reviewed hand')
        identity = (hand['table_id'], hand['hand_id_human_assigned'])
        if identity in identities:
            raise ValueError('Duplicate human-assigned hand identity')
        identities.add(identity)
        for event in hand['events']:
            if (not isinstance(event, dict) or not _number(event.get('timestamp'))
                    or not hand['first_observed_pts'] <= event['timestamp'] <= hand['last_observed_pts']
                    or type(event.get('observation_index')) is not int
                    or event['observation_index'] < 0
                    or event.get('human_reviewed_source') is not True
                    or event.get('not_authorized_for_equity_or_ev') is not True
                    or not _cards(event.get('board_visible'), (3, 4, 5))
                    or not _cards(event.get('hero_cards_visible'), (5, 6))
                    or any(v is not None and not _number(v) for v in
                           (event.get('pot_observed'), event.get('amount_observed')))
                    or not isinstance(event.get('field_evidence'), dict)):
                raise ValueError('Malformed reviewed timeline event')
        if (hand['events'][0]['timestamp'] != hand['first_observed_pts']
                or hand['events'][-1]['timestamp'] != hand['last_observed_pts']):
            raise ValueError('Hand PTS boundaries disagree with event order')
    return hands


def build_timeline_consistency_audit(timeline, *, expected_timeline_sha256=None,
                                     pot_drop_tolerance=0.01):
    """Audit only observed values within each human-assigned hand.

    Pot changes do not establish betting mistakes or even a real pot decrease.
    All reported flags require review of original frames and timestamps.
    """
    hands = _validate(timeline, expected_timeline_sha256)
    if not _number(pot_drop_tolerance) or pot_drop_tolerance > 1000000:
        raise ValueError('Invalid pot-drop tolerance')
    output = []
    totals = Counter()
    for hand in hands:
        flags = []
        previous_board = previous_hero = previous_pot = previous_variant = None
        previous_board_event = previous_hero_event = previous_pot_event = None
        previous_pts = None
        for event in hand['events']:
            index, pts = event['observation_index'], event['timestamp']
            refs = event['field_evidence']

            def flag(kind, prior=None, field=None):
                entry = {'kind': kind, 'observation_index': index, 'pts_seconds': pts,
                         'prior_observation_index': (prior['observation_index'] if prior else None),
                         'prior_pts_seconds': (prior['timestamp'] if prior else None),
                         'field': field,
                         'source_image_not_reaudited': (refs.get(field, {}).get('source_image')
                                                       if field else None),
                         'requires_manual_review': True}
                flags.append(entry)
                totals[kind] += 1

            if previous_pts is not None and pts < previous_pts:
                flag('non_monotonic_observation_pts')
            previous_pts = pts
            board, hero = event.get('board_visible'), event.get('hero_cards_visible')
            pot, variant = event.get('pot_observed'), event.get('variant_human_annotated')
            if board is not None:
                if previous_board is not None:
                    if len(board) < len(previous_board):
                        flag('board_card_count_regressed', previous_board_event, 'board')
                    elif board[:len(previous_board)] != previous_board:
                        flag('board_visible_prefix_changed', previous_board_event, 'board')
                    if pts == previous_board_event['timestamp'] and board != previous_board:
                        flag('same_pts_conflicting_board', previous_board_event, 'board')
                previous_board, previous_board_event = board, event
            if hero is not None:
                if previous_hero is not None and set(hero) != set(previous_hero):
                    flag('hero_cards_changed', previous_hero_event, 'hero_cards')
                if (previous_hero_event is not None and
                        pts == previous_hero_event['timestamp'] and set(hero) != set(previous_hero)):
                    flag('same_pts_conflicting_hero', previous_hero_event, 'hero_cards')
                previous_hero, previous_hero_event = hero, event
            # Compare only the last observed card sets. Never invent missing cards.
            if previous_board is not None and previous_hero is not None:
                if set(previous_board) & set(previous_hero) and (board is not None or hero is not None):
                    flag('visible_board_hero_collision', field='board' if board is not None else 'hero_cards')
            if pot is not None:
                if previous_pot is not None and pot + pot_drop_tolerance < previous_pot:
                    flag('pot_value_decreased_review_ui_or_payout', previous_pot_event, 'pot')
                if (previous_pot_event is not None and pts == previous_pot_event['timestamp']
                        and pot != previous_pot):
                    flag('same_pts_conflicting_pot', previous_pot_event, 'pot')
                previous_pot, previous_pot_event = pot, event
            if variant is not None:
                if previous_variant is not None and variant != previous_variant:
                    flag('variant_annotation_changed')
                previous_variant = variant
        output.append({'table_id': hand['table_id'],
                       'hand_id_human_assigned': hand['hand_id_human_assigned'],
                       'first_observed_pts': hand['first_observed_pts'],
                       'last_observed_pts': hand['last_observed_pts'],
                       'source_timeline_review_flags': hand['review_flags'],
                       'audit_flags': flags, 'human_review_required': True,
                       'reconstructed_hand_verified': False})
    return {'schema_version': 1,
            'analysis_status': 'review_only_timeline_consistency_hints',
            'recording_sha256': timeline['recording_sha256'],
            'source_timeline_sha256': canonical_sha256(timeline),
            'timestamp_semantics': timeline['timestamp_semantics'],
            'hands': output,
            'counts': {'hands': len(output), 'hands_with_audit_flags':
                       sum(bool(x['audit_flags']) for x in output),
                       'audit_flags': sum(totals.values()), 'flags_by_kind': dict(sorted(totals.items()))},
            'requires_manual_review': True,
            'ready_for_equity_or_ev': False,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': ('Synthetic or human-reviewed labels are not verified video truth. '
                        'Pot drops may reflect payouts, side pots, OCR or UI changes. '
                        'No hidden cards, exact transitions, ranges, EV, errors or clips inferred.')}


def write_timeline_consistency_audit(input_json, output_json, **kwargs):
    source, target = Path(input_json), Path(output_json)
    if (not source.is_file() or source.is_symlink() or target.exists()
            or target.is_symlink() or source.resolve() == target.resolve()):
        raise ValueError('Require regular input and a new distinct output')
    data = json.loads(source.read_text(encoding='utf-8'))
    result = build_timeline_consistency_audit(data, **kwargs)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as fp:
        json.dump(result, fp, indent=2, ensure_ascii=False, allow_nan=False)
        fp.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--expected-timeline-sha256')
    args = parser.parse_args()
    report = write_timeline_consistency_audit(args.reviewed_timeline_json, args.output_json,
                        expected_timeline_sha256=args.expected_timeline_sha256)
    print(json.dumps(report['counts'], sort_keys=True))
