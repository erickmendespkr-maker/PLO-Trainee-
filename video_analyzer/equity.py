"""Reproducible heads-up PLO5/PLO6 showdown equity.

Only exactly two hole cards and three board cards form a hand.
Uniform random opponents are NOT a strategic range. CI covers Monte Carlo
sampling uncertainty only, not range plausibility or OCR uncertainty.
No rake, future betting, side pots, multiway pots, or ICM.
"""
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
import math
import random

from hand_history import validate_cards

DECK = tuple(r + s for r in '23456789TJQKA' for s in 'cdhs')
VALUE = {r: i + 2 for i, r in enumerate('23456789TJQKA')}


def rank_five(cards):
    """Standard high-hand rank, comparable lexicographically."""
    validate_cards(cards)
    if len(cards) != 5:
        raise ValueError('Five cards required')
    ranks = [VALUE[c[0]] for c in cards]
    counts = Counter(ranks)
    by_count = sorted(((n, rank) for rank, n in counts.items()), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    unique = set(ranks)
    if 14 in unique:
        unique.add(1)
    straight_high = next((high for high in range(14, 4, -1)
                          if set(range(high - 4, high + 1)).issubset(unique)), None)
    if flush and straight_high:
        return (8, straight_high)
    if by_count[0][0] == 4:
        return (7, by_count[0][1], by_count[1][1])
    if [p[0] for p in by_count] == [3, 2]:
        return (6, by_count[0][1], by_count[1][1])
    if flush:
        return (5, *sorted(ranks, reverse=True))
    if straight_high:
        return (4, straight_high)
    if by_count[0][0] == 3:
        return (3, by_count[0][1], *sorted((r for r in ranks if r != by_count[0][1]), reverse=True))
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    if len(pairs) == 2:
        return (2, *pairs, next(r for r, n in counts.items() if n == 1))
    if len(pairs) == 1:
        return (1, pairs[0], *sorted((r for r in ranks if r != pairs[0]), reverse=True))
    return (0, *sorted(ranks, reverse=True))


def omaha_rank(hole, board):
    """PLO5/PLO6: exactly two private and three community cards."""
    validate_cards(hole)
    validate_cards(board)
    validate_cards(tuple(hole) + tuple(board))
    if len(hole) not in (5, 6) or len(board) != 5:
        raise ValueError('PLO5/PLO6 requires 5/6 private cards and 5 board cards')
    return max(rank_five(two + three) for two in combinations(hole, 2)
               for three in combinations(board, 3))


@dataclass(frozen=True)
class EquityResult:
    variant: str
    trials: int
    seed: int
    opponent_model: str
    wins: int
    ties: int
    losses: int
    equity: float
    ci95_low: float
    ci95_high: float


def bounded_ci95(equity, trials, *, deterministic=False):
    """Conservative Hoeffding CI for independent fractional-win samples [0,1]."""
    if deterministic:
        return equity, equity
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError('trials must be positive')
    radius = math.sqrt(math.log(40.) / (2. * trials))
    return max(0., equity - radius), min(1., equity + radius)


def estimate_equity(hero, board, *, opponent=None, trials=1000, seed=0):
    """Monte Carlo showdown equity; opponent=None means uniform random cards."""
    hero, board = tuple(hero), tuple(board)
    opponent = tuple(opponent) if opponent is not None else None
    validate_cards(hero)
    validate_cards(board)
    if len(hero) not in (5, 6) or not 0 <= len(board) <= 5:
        raise ValueError('Only PLO5/PLO6 and board sizes 0..5 supported')
    if opponent is not None:
        validate_cards(opponent)
        if len(opponent) != len(hero):
            raise ValueError('Opponent must have same number of private cards')
    validate_cards(hero + board + (opponent or ()))
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError('trials must be a positive integer')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    blocked = set(hero + board + (opponent or ()))
    remaining = tuple(c for c in DECK if c not in blocked)
    needed = 5 - len(board) + (0 if opponent is not None else len(hero))
    if len(remaining) < needed:
        raise ValueError('Not enough cards to sample')
    rng = random.Random(seed)
    wins = ties = losses = 0
    for _ in range(trials):
        sampled = rng.sample(remaining, needed)
        full_board = board + tuple(sampled[:5 - len(board)])
        villain = opponent if opponent is not None else tuple(sampled[5 - len(board):])
        a = omaha_rank(hero, full_board)
        b = omaha_rank(villain, full_board)
        wins += a > b
        ties += a == b
        losses += a < b
    equity = (wins + .5 * ties) / trials
    low, high = bounded_ci95(equity, trials, deterministic=opponent is not None and len(board) == 5)
    return EquityResult(f'PLO{len(hero)}', trials, seed,
                        'known_opponent' if opponent is not None else 'uniform_random_opponent',
                        wins, ties, losses, equity, low, high)


def simplified_call_ev(equity, pot_before_call, call_amount):
    """Net heads-up all-in call EV relative to folding=0; no future betting."""
    if isinstance(equity, bool) or not isinstance(equity, (int, float)) or not math.isfinite(equity) or not 0 <= equity <= 1:
        raise ValueError('equity must be between zero and one')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0
           for x in (pot_before_call, call_amount)):
        raise ValueError('Pot and call must be nonnegative finite numbers')
    return equity * (pot_before_call + call_amount) - call_amount
