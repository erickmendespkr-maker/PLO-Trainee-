"""Typed, conservative offline observations; no inference of unseen poker actions.

Input observations are manually annotated or produced by future OCR/vision.
Every field may be absent; confidence must be provided for observed fields.
"""
from dataclasses import dataclass, field, asdict
import json
import math
from pathlib import Path

RANKS = set('23456789TJQKA')
SUITS = set('cdhs')
ACTIONS = {'hand_start', 'fold', 'check', 'call', 'bet', 'raise', 'board', 'showdown', 'hand_end'}


def validate_cards(cards):
    if not isinstance(cards, (list, tuple)):
        raise ValueError('Cards must be a list')
    if any(not isinstance(c, str) or len(c) != 2 or c[0] not in RANKS or c[1] not in SUITS for c in cards):
        raise ValueError('Invalid card notation; use e.g. As, Td')
    if len(cards) != len(set(cards)):
        raise ValueError('Duplicate cards')


@dataclass(frozen=True)
class Observation:
    table_id: int
    timestamp: float
    action: str
    confidence: float
    hand_id: str | None = None
    actor: str | None = None
    amount: float | None = None
    pot: float | None = None
    board: tuple[str, ...] | None = None
    hero_cards: tuple[str, ...] | None = None
    variant: str | None = None
    notes: str = ''
    field_confidence: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.table_id, int) or not 1 <= self.table_id <= 4:
            raise ValueError('table_id must be 1..4')
        if not math.isfinite(self.timestamp) or self.timestamp < 0:
            raise ValueError('timestamp must be finite and nonnegative')
        if self.action not in ACTIONS:
            raise ValueError('Unknown action')
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError('Invalid observation confidence')
        for key, value in self.field_confidence.items():
            if key not in {'action', 'actor', 'amount', 'pot', 'board', 'hero_cards', 'variant'}:
                raise ValueError('Unknown confidence field')
            if not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid field confidence')
        for v in (self.amount, self.pot):
            if v is not None and (not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0):
                raise ValueError('Amounts must be finite and nonnegative')
        if self.variant is not None and self.variant not in {'PLO5', 'PLO6'}:
            raise ValueError('Only PLO5/PLO6 supported')
        if self.board is not None:
            validate_cards(self.board)
            if len(self.board) > 5:
                raise ValueError('Board cannot exceed five cards')
        if self.hero_cards is not None:
            validate_cards(self.hero_cards)
            if self.variant and len(self.hero_cards) != int(self.variant[-1]):
                raise ValueError('Incorrect number of private cards')
        if self.board is not None and self.hero_cards is not None:
            validate_cards(tuple(self.board) + tuple(self.hero_cards))


def reconstruct_hands(observations):
    """Group annotated observations by (table_id, hand_id) without inventing hands.

    Observations without a hand_id remain unassigned for manual review.
    Timestamps must be nondecreasing per table, including between hands.
    """
    hands = {}
    unassigned = []
    last_time = {}
    for obs in observations:
        if not isinstance(obs, Observation):
            raise TypeError('Expected Observation')
        if obs.timestamp < last_time.get(obs.table_id, -1):
            raise ValueError('Observations out of order within table')
        last_time[obs.table_id] = obs.timestamp
        if not obs.hand_id:
            unassigned.append(obs)
            continue
        key = (obs.table_id, obs.hand_id)
        hands.setdefault(key, []).append(obs)
    return hands, unassigned


def export_history(observations, destination):
    """Write versioned JSON; preserve uncertainties and per-field confidence."""
    hands, unassigned = reconstruct_hands(observations)
    result = {
        'schema_version': 1,
        'hands': [
            {'table_id': table, 'hand_id': hand, 'observations': [asdict(o) for o in obs]}
            for (table, hand), obs in hands.items()
        ],
        'unassigned': [asdict(o) for o in unassigned],
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return json.loads(destination.read_text(encoding='utf-8'))
