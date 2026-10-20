"""Conservative offline audit of annotated PLO5/PLO6 hand observations.

This is a consistency checker, NOT a poker action detector or strategy solver.
No unobserved action, hidden card or hand boundary is invented.
"""
from dataclasses import asdict
import json
from pathlib import Path

from hand_history import Observation, reconstruct_hands, validate_cards


def audit_observations(observations, *, min_confidence=0.75):
    """Produce per-hand review flags and preserve unassigned observations.

    Consistency is not evidence that a hand was recognized correctly. The
    confidence fields are supplied by annotators/engines and are uncalibrated.
    """
    if isinstance(min_confidence, bool) or not isinstance(min_confidence, (int, float)) or not 0 <= min_confidence <= 1:
        raise ValueError('min_confidence must be in [0,1]')
    hands, unassigned = reconstruct_hands(observations)
    summaries = []
    for (table_id, hand_id), events in hands.items():
        flags = set()
        variants = {event.variant for event in events if event.variant is not None}
        if len(variants) > 1:
            flags.add('conflicting_variants')
        variant = next(iter(variants)) if len(variants) == 1 else None
        if variant is None:
            flags.add('missing_or_conflicting_variant')
        starts = [event for event in events if event.action == 'hand_start']
        ends = [event for event in events if event.action == 'hand_end']
        if len(starts) != 1:
            flags.add('missing_or_multiple_hand_start')
        if len(ends) != 1:
            flags.add('missing_or_multiple_hand_end')
        if starts and ends and starts[0].timestamp > ends[-1].timestamp:
            flags.add('end_before_start')
        if starts and events[0].action != 'hand_start':
            flags.add('action_before_start')
        if ends and events[-1].action != 'hand_end':
            flags.add('action_after_end')
        boards = []
        private = []
        for event in events:
            if event.confidence < min_confidence or any(value < min_confidence for value in event.field_confidence.values()):
                flags.add('low_observation_confidence')
            if event.board is not None:
                board = tuple(event.board)
                if len(board) not in (0, 3, 4, 5):
                    flags.add('incomplete_or_invalid_street')
                if boards and (len(board) < len(boards[-1]) or board[:len(boards[-1])] != boards[-1]):
                    flags.add('board_regression_or_conflict')
                boards.append(board)
            if event.hero_cards is not None:
                hole = tuple(event.hero_cards)
                if variant and len(hole) != int(variant[-1]):
                    flags.add('incorrect_private_card_count')
                if private and hole != private[-1]:
                    flags.add('private_cards_conflict')
                private.append(hole)
        if boards and private:
            try:
                validate_cards(boards[-1] + private[-1])
            except ValueError:
                flags.add('board_private_card_conflict')
        summaries.append({
            'table_id': table_id, 'hand_id': hand_id, 'variant': variant,
            'first_timestamp': events[0].timestamp,
            'last_timestamp': events[-1].timestamp,
            'observation_count': len(events),
            'observed_actions': [e.action for e in events],
            'latest_visible_board': list(boards[-1]) if boards else None,
            'latest_visible_private_cards': list(private[-1]) if private else None,
            'flags': sorted(flags),
            'review_status': 'needs_manual_review' if flags else 'annotated_consistent_unverified',
        })
    # Flag overlapping hands on the same table without guessing attribution.
    for index, a in enumerate(summaries):
        for b in summaries[index + 1:]:
            if a['table_id'] != b['table_id']:
                continue
            if a['first_timestamp'] < b['last_timestamp'] and b['first_timestamp'] < a['last_timestamp']:
                for item in (a, b):
                    item['flags'] = sorted(set(item['flags']) | {'overlapping_hand_timestamps'})
                    item['review_status'] = 'needs_manual_review'
    return {
        'schema_version': 1,
        'analysis_status': 'manual_or_unverified_observations_only',
        'confidence_note': 'Confidence scores are not calibrated probabilities of correct poker-state reconstruction.',
        'hands': summaries,
        'unassigned': [asdict(event) for event in unassigned],
        'counts': {
            'hands': len(summaries),
            'needs_manual_review': sum(h['review_status'] == 'needs_manual_review' for h in summaries),
            'unassigned_observations': len(unassigned),
        },
    }


def audit_json(source, destination, *, min_confidence=0.75):
    """Read a JSON list of Observation dictionaries and save the audit."""
    source = Path(source)
    raw = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        raise ValueError('Input must be a JSON list of observations')
    observations = [Observation(**entry) for entry in raw]
    report = audit_observations(observations, min_confidence=min_confidence)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations_json')
    parser.add_argument('report_json')
    parser.add_argument('--min-confidence', type=float, default=0.75)
    args = parser.parse_args()
    report = audit_json(args.observations_json, args.report_json, min_confidence=args.min_confidence)
    print(json.dumps(report['counts'], ensure_ascii=False))
