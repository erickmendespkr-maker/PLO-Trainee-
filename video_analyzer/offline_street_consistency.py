"""Conservative consistency checks for recorded Omaha board observations.

Never infers hidden cards, unseen actions or strategic correctness.
"""
from dataclasses import dataclass
from typing import Optional, Sequence

STREETS = {'preflop': 0, 'flop': 3, 'turn': 4, 'river': 5}
RANKS = set('23456789TJQKA')
SUITS = set('cdhs')


@dataclass(frozen=True)
class Observation:
    pts_seconds: float
    street: str
    board: tuple[str, ...]
    table_id: int
    hand_id: str
    confidence: float


def validate_observation(obs: Observation, hole_cards: Optional[Sequence[str]] = None,
                         variant: Optional[str] = None) -> list[str]:
    errors = []
    if not isinstance(obs.pts_seconds, (int, float)) or not (0 <= obs.pts_seconds < float('inf')):
        errors.append('invalid_pts')
    if obs.street not in STREETS:
        errors.append('unknown_street')
    elif len(obs.board) != STREETS[obs.street]:
        errors.append('board_count_street_mismatch')
    if not isinstance(obs.table_id, int) or isinstance(obs.table_id, bool) or not 1 <= obs.table_id <= 4:
        errors.append('invalid_table')
    if not isinstance(obs.hand_id, str) or not obs.hand_id.strip():
        errors.append('missing_hand_id')
    if not isinstance(obs.confidence, (int, float)) or not (0 <= obs.confidence <= 1):
        errors.append('invalid_confidence')
    cards = list(obs.board)
    if hole_cards is not None:
        if variant not in ('PLO5', 'PLO6') or len(hole_cards) != int(variant[-1]):
            errors.append('hole_count_variant_mismatch')
        cards.extend(hole_cards)
    for card in cards:
        if not isinstance(card, str) or len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
            errors.append('invalid_card')
            break
    if len(set(cards)) != len(cards):
        errors.append('duplicate_card')
    return errors


def review_sequence(observations: Sequence[Observation]) -> dict:
    """Review one hand/table; gaps remain unknown rather than invented."""
    if not observations:
        return {'status': 'INSUFFICIENT_DATA', 'errors': ['empty_sequence']}
    errors = []
    first = observations[0]
    prev = None
    for obs in observations:
        errors.extend(validate_observation(obs))
        if (obs.table_id, obs.hand_id) != (first.table_id, first.hand_id):
            errors.append('mixed_hand_or_table')
        if prev is not None:
            if obs.pts_seconds <= prev.pts_seconds:
                errors.append('non_increasing_pts')
            if obs.street in STREETS and prev.street in STREETS:
                if STREETS[obs.street] < STREETS[prev.street]:
                    errors.append('street_regression')
                if len(obs.board) >= len(prev.board) and obs.board[:len(prev.board)] != prev.board:
                    errors.append('board_changed')
        prev = obs
    errors = sorted(set(errors))
    return {'status': 'REVIEW_REQUIRED' if errors else 'CONSISTENT_OBSERVATIONS_ONLY',
            'errors': errors, 'observation_count': len(observations),
            'verified_by_human': False, 'strategic_conclusion_allowed': False}
