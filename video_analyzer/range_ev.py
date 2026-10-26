"""Transparent, offline heads-up PLO5/PLO6 *scenario* equity and simplified EV.

A weighted range is an explicitly provided set of opponent hands and weights.
These are assumptions, NOT ranges learned from a video or a GTO solver.
All EV formulas assume no future betting, rake, side pots, or ICM.
"""
from dataclasses import dataclass
from math import isfinite, fsum
import random

from equity import DECK, EquityResult, omaha_rank, bounded_ci95
from hand_history import validate_cards


@dataclass(frozen=True)
class WeightedHand:
    cards: tuple[str, ...]
    weight: float


def _probability(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'{label} must be a finite probability in [0,1]')
    return float(value)


def _nonnegative(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f'{label} must be finite and nonnegative')
    return float(value)


def estimate_weighted_range_equity(hero, board, weighted_range, *, trials=1000, seed=0):
    """Monte Carlo showdown equity versus a *user-supplied* weighted range.

    The opponent hand is drawn by its relative weight, then unknown board cards
    are drawn uniformly without replacement. All opponent hands must be valid
    and compatible with visible hero/board cards. This is heads-up only.
    """
    hero, board = tuple(hero), tuple(board)
    validate_cards(hero)
    validate_cards(board)
    validate_cards(hero + board)
    if len(hero) not in (5, 6) or len(board) > 5:
        raise ValueError('PLO5/PLO6 requires 5 or 6 hero cards and at most 5 board cards')
    if isinstance(trials, bool) or not isinstance(trials, int) or not 1 <= trials <= 50000:
        raise ValueError('trials must be an integer from 1 to 50000')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    hands, weights, decks = [], [], []
    seen = set()
    for count, entry in enumerate(weighted_range):
        if count >= 10000:
            raise ValueError('Range exceeds 10000 opponent hands')
        if not isinstance(entry, WeightedHand):
            raise TypeError('Range entries must be WeightedHand')
        cards = tuple(entry.cards)
        validate_cards(cards)
        if len(cards) != len(hero):
            raise ValueError('Opponent must have the same number of private cards')
        validate_cards(hero + board + cards)
        key = tuple(sorted(cards))
        if key in seen:
            raise ValueError('Duplicate opponent hand in range')
        seen.add(key)
        weight = _nonnegative(entry.weight, 'range weight')
        if weight == 0:
            continue
        blocked = set(hero + board + cards)
        remaining = tuple(c for c in DECK if c not in blocked)
        if len(remaining) < 5 - len(board):
            raise ValueError('Not enough remaining board cards')
        hands.append(cards)
        weights.append(weight)
        decks.append(remaining)
    if not hands:
        raise ValueError('Range must contain a positive-weight hand')
    try:
        total_weight = fsum(weights)
    except OverflowError as exc:
        raise ValueError('Sum of range weights must be finite') from exc
    if not isfinite(total_weight):
        raise ValueError('Sum of range weights must be finite')
    rng = random.Random(seed)
    wins = ties = losses = 0
    for _ in range(trials):
        idx = rng.choices(range(len(hands)), weights=weights, k=1)[0]
        full_board = board + tuple(rng.sample(decks[idx], 5 - len(board)))
        hero_rank = omaha_rank(hero, full_board)
        villain_rank = omaha_rank(hands[idx], full_board)
        wins += hero_rank > villain_rank
        ties += hero_rank == villain_rank
        losses += hero_rank < villain_rank
    equity = (wins + .5 * ties) / trials
    low, high = bounded_ci95(equity, trials, deterministic=len(hands) == 1 and len(board) == 5)
    return EquityResult(f'PLO{len(hero)}', trials, seed, 'user_weighted_opponent_range',
                        wins, ties, losses, equity, low, high)


def heads_up_all_in_raise_ev(equity_when_called, pot_before_raise, hero_extra_chips,
                              villain_extra_chips_if_called, fold_probability):
    """Net EV of a raise vs folding now (fold baseline = 0).

    pot_before_raise includes all money already in the pot (including previous
    bets). hero_extra_chips is the incremental amount invested by hero now;
    villain_extra_chips_if_called is opponent's additional call amount.
    Opponent folds with the supplied probability, otherwise calls; no later
    betting, rake, side pots or ICM. When villain folds, hero wins the old pot.
    """
    equity = _probability(equity_when_called, 'equity_when_called')
    fold = _probability(fold_probability, 'fold_probability')
    pot = _nonnegative(pot_before_raise, 'pot_before_raise')
    hero = _nonnegative(hero_extra_chips, 'hero_extra_chips')
    villain = _nonnegative(villain_extra_chips_if_called, 'villain_extra_chips_if_called')
    called_ev = equity * (pot + hero + villain) - hero
    return fold * pot + (1. - fold) * called_ev
