"""Conservative per-decision snapshots from *annotated* offline PLO5/PLO6 events.

Snapshots are review hints, NOT authenticated video observations, poker-state
reconstructions, equity inputs, or executable EV scenarios. In particular,
observations at the same timestamp are excluded to avoid order ambiguity.
"""
import argparse
import json
import math
from pathlib import Path

from hand_history import Observation, reconstruct_hands
from observation_audit import audit_observations

DECISIONS = frozenset({'fold', 'call', 'raise'})
VISIBLE_FIELDS = ('hero_cards', 'board', 'pot')


def _bounded(value, label, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= 0 if positive else not 0 <= value <= 1)):
        raise ValueError(f'Invalid {label}')
    return float(value)


def build_decision_snapshots(observations, *, min_confidence=.75, max_age_seconds=30.):
    """Produce a review-only queue without carrying information from the future.

    Each hint must have been observed at a STRICTLY earlier timestamp, in the
    same table and hand. Field confidence is self-reported and uncalibrated.
    Missing ranges/call amounts are NEVER filled in from OCR or prior actions.
    """
    minimum = _bounded(min_confidence, 'min_confidence')
    age_limit = _bounded(max_age_seconds, 'max_age_seconds', positive=True)
    if not isinstance(observations, (list, tuple)) or len(observations) > 100000:
        raise ValueError('Expected at most 100000 observations')
    if any(not isinstance(item, Observation) for item in observations):
        raise TypeError('All observations must be Observation objects')
    hands, unassigned = reconstruct_hands(observations)
    audit = audit_observations(observations, min_confidence=minimum)
    audit_by_key = {(row['table_id'], row['hand_id']): row for row in audit['hands']}
    indices = {}
    for index, event in enumerate(observations):
        indices.setdefault(id(event), []).append(index)
    if any(len(positions) != 1 for positions in indices.values()):
        raise ValueError('Repeated Observation object reference is ambiguous')
    tasks = []
    for key, events in hands.items():
        table, hand = key
        audit_flags = audit_by_key[key]['flags']
        for decision in events:
            if decision.action not in DECISIONS:
                continue
            hints = {}
            blockers = {'call_amount_requires_manual_confirmation',
                        'opponent_range_requires_manual_input',
                        'all_in_model_assumptions_require_manual_review'}
            for field in VISIBLE_FIELDS:
                candidates = [e for e in events if e.timestamp < decision.timestamp
                              and getattr(e, field) is not None]
                if not candidates:
                    hints[field] = None
                    blockers.add(f'{field}_not_observed_before_decision')
                    continue
                source = candidates[-1]
                confidence = source.field_confidence.get(field, source.confidence)
                elapsed = decision.timestamp - source.timestamp
                if confidence < minimum:
                    blockers.add(f'{field}_low_subjective_confidence')
                if elapsed > age_limit:
                    blockers.add(f'{field}_stale_observation')
                hints[field] = {
                    'value': list(getattr(source, field)) if field in ('hero_cards', 'board')
                             else getattr(source, field),
                    'source_timestamp': source.timestamp,
                    'source_observation_index': indices[id(source)][0],
                    'subjective_confidence': confidence,
                    'age_seconds': elapsed,
                    'human_confirmed': False,
                }
            if decision.confidence < minimum or decision.field_confidence.get('action', decision.confidence) < minimum:
                blockers.add('action_low_subjective_confidence')
            if decision.actor is None:
                blockers.add('actor_not_confirmed')
            if audit_flags:
                blockers.add('hand_consistency_flags_require_review')
            tasks.append({
                'table_id': table, 'hand_id': hand,
                'decision_timestamp': decision.timestamp,
                'decision_observation_index': indices[id(decision)][0],
                'observed_action_hint': decision.action,
                'actor_hint': decision.actor,
                'visible_hints_unverified': hints,
                'hand_audit_flags': list(audit_flags),
                'blockers': sorted(blockers),
                'ready_for_ev': False,
                'human_confirmed': False,
            })
    tasks.sort(key=lambda row: (row['decision_timestamp'], row['table_id'], row['decision_observation_index']))
    return {
        'schema_version': 1,
        'analysis_status': 'offline_annotated_decision_snapshots_unverified',
        'tasks': tasks,
        'counts': {'decisions': len(tasks), 'hands': len(hands),
                   'unassigned_observations': len(unassigned), 'ready_for_ev': 0},
        'warning': ('Snapshots contain only earlier annotated observations, not video-verified facts. '
                    'No opponent range, call amount, hidden card, equity or EV is inferred. '
                    'Confidence is subjective and uncalibrated.'),
    }


def snapshots_json(input_path, output_path, *, min_confidence=.75, max_age_seconds=30.):
    """Create a new JSON report without overwriting input or existing files."""
    source, destination = Path(input_path), Path(output_path)
    if destination.resolve() == source.resolve() or destination.exists():
        raise ValueError('Output must be a new file distinct from input')
    raw = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        raise ValueError('Input must be a list of observations')
    result = build_decision_snapshots([Observation(**item) for item in raw],
                                      min_confidence=min_confidence,
                                      max_age_seconds=max_age_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations_json')
    parser.add_argument('output_json')
    parser.add_argument('--min-confidence', type=float, default=.75)
    parser.add_argument('--max-age', type=float, default=30.)
    args = parser.parse_args()
    report = snapshots_json(args.observations_json, args.output_json,
                            min_confidence=args.min_confidence, max_age_seconds=args.max_age)
    print(json.dumps(report['counts']))
