"""Conservative, provenance-linked timeline from human-reviewed offline OCR observations.

A timeline is NOT an automatically reconstructed poker hand. Hand identifiers,
player actions, and OCR labels originate from human review and remain uncertain.
Board transitions describe visible changes, not the exact moment cards appeared.
No ranges, equity, EV, or clip-selection permissions are created here.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from activity_snapshot_chain import build_activity_snapshot_queue, canonical_sha256
from hand_history import Observation

STREETS = {0: 'preflop_visible_board', 3: 'flop_visible_board',
           4: 'turn_visible_board', 5: 'river_visible_board'}
CARD_FIELDS = ('hero_cards', 'board')


def _cards(value):
    return list(value) if value is not None else None


def _transition(previous, current):
    """Classify board observations, without treating changes as hand boundaries."""
    if previous == current:
        return 'unchanged'
    if len(current) > len(previous) and current[:len(previous)] == previous:
        return 'compatible_extension'
    return 'incompatible_visible_board_change'


def build_reviewed_hand_timeline(reviewed, *, expected_review_sha256=None):
    """Validate upstream provenance then group only explicitly assigned hands.

    Never borrow a future board or private card for an earlier decision. An
    unknown hand ID stays unassigned, even if neighboring observations match.
    """
    queue = build_activity_snapshot_queue(
        reviewed, expected_review_sha256=expected_review_sha256)
    observations = [Observation(**row) for row in reviewed['observations']]
    provenance = reviewed['provenance']
    grouped = defaultdict(list)
    unassigned = []
    table_sequence = defaultdict(list)
    for index, obs in enumerate(observations):
        if obs.hand_id is None:
            unassigned.append({'observation_index': index, 'table_id': obs.table_id,
                               'timestamp': obs.timestamp,
                               'reason': 'hand_id_not_human_assigned',
                               'human_annotated_action': obs.action,
                               'reviewed_field_evidence': [{
                                   'field': item['field'],
                                   'source_image': item['source_image'],
                                   'decoded_source_pts': item['source_timestamp'],
                                   'candidate_index': item['candidate_index'],
                               } for item in provenance[index]['evidence']]})
        else:
            key = (obs.table_id, obs.hand_id)
            grouped[key].append(index)
            table_sequence[obs.table_id].append((index, obs.hand_id))

    interleaved = set()
    for table, items in table_sequence.items():
        closed = set()
        last_hand = None
        for _, hand in items:
            if hand != last_hand:
                if last_hand is not None:
                    closed.add(last_hand)
                if hand in closed:
                    interleaved.add((table, hand))
                last_hand = hand

    hands = []
    for (table, hand_id), indices in sorted(
            grouped.items(), key=lambda pair: (pair[1][0], pair[0])):
        issues = set()
        if (table, hand_id) in interleaved:
            issues.add('interleaved_hand_identity_requires_review')
        first_start = None
        last_end = None
        starts = ends = 0
        previous_board = None
        previous_board_timestamp = None
        previous_hero = None
        previous_variant = None
        events = []
        for index in indices:
            obs = observations[index]
            if obs.action == 'hand_start':
                starts += 1
                if first_start is None:
                    first_start = obs.timestamp
                if starts > 1 or last_end is not None:
                    issues.add('repeated_or_post_end_hand_start')
            elif obs.action == 'hand_end':
                ends += 1
                last_end = obs.timestamp
                if starts == 0:
                    issues.add('end_without_observed_start')
                if ends > 1:
                    issues.add('repeated_hand_end')
            elif last_end is not None:
                issues.add('event_after_observed_hand_end')

            if obs.variant is not None:
                if previous_variant is not None and previous_variant != obs.variant:
                    issues.add('variant_changed_within_hand')
                previous_variant = obs.variant
            if obs.hero_cards is not None:
                if previous_hero is not None and set(previous_hero) != set(obs.hero_cards):
                    issues.add('private_cards_changed_within_hand')
                previous_hero = obs.hero_cards
            if obs.board is not None and previous_hero is not None:
                if set(obs.board) & set(previous_hero):
                    issues.add('visible_board_private_card_collision')
            if obs.hero_cards is not None and previous_board is not None:
                if set(obs.hero_cards) & set(previous_board):
                    issues.add('visible_board_private_card_collision')

            transition = None
            if obs.board is not None:
                if len(obs.board) not in STREETS:
                    issues.add('nonstandard_visible_board_card_count')
                if previous_board is not None:
                    transition = {
                        'kind': _transition(previous_board, obs.board),
                        'from_timestamp': previous_board_timestamp,
                        'to_timestamp': obs.timestamp,
                        'exact_change_time_known': False,
                    }
                    if transition['kind'] == 'incompatible_visible_board_change':
                        issues.add('incompatible_board_progression_requires_review')
                    if (transition['kind'] != 'unchanged'
                            and previous_board_timestamp == obs.timestamp):
                        issues.add('same_pts_conflicting_board_observations')
                previous_board = obs.board
                previous_board_timestamp = obs.timestamp

            source = provenance[index]
            refs = {entry['field']: {
                'candidate_index': entry['candidate_index'],
                'source_image': entry['source_image'],
                'decoded_source_pts': entry['source_timestamp'],
                'reviewer_confidence_subjective': entry['reviewer_confidence'],
            } for entry in source['evidence']}
            events.append({
                'observation_index': index, 'timestamp': obs.timestamp,
                'action_human_annotated_not_ocr_verified': obs.action,
                'actor_human_annotated': obs.actor,
                'amount_observed': obs.amount, 'pot_observed': obs.pot,
                'board_visible': _cards(obs.board),
                'hero_cards_visible': _cards(obs.hero_cards),
                'variant_human_annotated': obs.variant,
                'visible_street_hint': (STREETS.get(len(obs.board))
                                        if obs.board is not None else None),
                'board_transition': transition,
                'field_evidence': refs,
                'action_subjective_confidence': obs.field_confidence.get('action', obs.confidence),
                'human_reviewed_source': True,
                'not_authorized_for_equity_or_ev': True,
            })
        if starts == 0:
            issues.add('hand_start_not_observed')
        if ends == 0:
            issues.add('hand_end_not_observed')
        hands.append({
            'table_id': table, 'hand_id_human_assigned': hand_id,
            'first_observed_pts': events[0]['timestamp'],
            'last_observed_pts': events[-1]['timestamp'],
            'hand_start_observed_pts': first_start,
            'hand_end_observed_pts': last_end,
            'observation_count': len(events),
            'review_flags': sorted(issues),
            'events': events,
            'human_review_required': True,
        })

    return {
        'schema_version': 1,
        'analysis_status': 'human_reviewed_visible_timeline_not_verified_hand_reconstruction',
        'source_review_sha256': canonical_sha256(reviewed),
        'recording_sha256': queue['recording_sha256'],
        'timestamp_semantics': queue['timestamp_semantics'],
        'hands': hands,
        'unassigned_observations': unassigned,
        'counts': {'hands_human_assigned': len(hands),
                   'unassigned_observations': len(unassigned),
                   'hands_with_review_flags': sum(bool(h['review_flags']) for h in hands),
                   'observations': len(observations)},
        'ready_for_equity_or_ev': False,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Human-reviewed OCR labels and annotated actions are not authenticated '
                    'video truth. Card visibility is time-local; board transitions are '
                    'bounded between decoded PTS samples, not exact events. '
                    'No unseen cards, opponent ranges, betting actions, EV or errors inferred.'),
    }


def write_reviewed_hand_timeline(review_json, output_json, *, expected_review_sha256=None):
    source, output = Path(review_json), Path(output_json)
    if (not source.is_file() or source.is_symlink() or output.exists()
            or output.is_symlink() or source.resolve() == output.resolve()):
        raise ValueError('Require a regular input and a new distinct output')
    report = json.loads(source.read_text(encoding='utf-8'))
    result = build_reviewed_hand_timeline(report, expected_review_sha256=expected_review_sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as fp:
        json.dump(result, fp, indent=2, ensure_ascii=False, allow_nan=False)
        fp.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_activity_json')
    parser.add_argument('output_json')
    parser.add_argument('--expected-review-sha256')
    args = parser.parse_args()
    result = write_reviewed_hand_timeline(args.reviewed_activity_json, args.output_json,
                                          expected_review_sha256=args.expected_review_sha256)
    print(json.dumps(result['counts']))
