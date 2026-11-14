"""Offline reproducible PLO5/PLO6 showdown Monte Carlo; hypothetical ranges, not GTO."""
import random
from .offline_omaha_showdown import RANKS, SUITS, _cards, showdown_shares

DECK = tuple(r + s for r in RANKS for s in SUITS)

def sample_showdown_shares(*, hero, board, opponent_ranges, iterations=1000, seed=0, max_attempts=None):
    """Uniform independent range draws conditioned on no collisions (rejection sampling)."""
    if not isinstance(hero, (list, tuple)) or len(hero) not in (5, 6):
        raise ValueError("hero requires PLO5 or PLO6")
    hero = _cards(hero, len(hero))
    if not isinstance(board, (list, tuple)) or len(board) > 5:
        raise ValueError("board requires zero to five cards")
    board = _cards(board, len(board))
    if len(set(hero + board)) != len(hero) + len(board):
        raise ValueError("hero/board overlap")
    if not isinstance(opponent_ranges, (list, tuple)) or not 1 <= len(opponent_ranges) <= 5:
        raise ValueError("requires one to five opponent ranges")
    if type(iterations) is not int or not 1 <= iterations <= 1000000:
        raise ValueError("invalid iterations")
    if type(seed) is not int:
        raise ValueError("seed must be integer")
    if max_attempts is None:
        max_attempts = max(1000, iterations * 100)
    if type(max_attempts) is not int or max_attempts < iterations:
        raise ValueError("invalid max_attempts")
    ranges = []
    for group in opponent_ranges:
        if not isinstance(group, (list, tuple)) or not group:
            raise ValueError("empty opponent range")
        combos = []
        for combo in group:
            if not isinstance(combo, (list, tuple)) or len(combo) != len(hero):
                raise ValueError("opponent combo must match hero variant")
            combos.append(_cards(combo, len(hero)))
        if len(set(combos)) != len(combos):
            raise ValueError("duplicate range combo")
        ranges.append(combos)
    if len(hero) * (len(ranges) + 1) + 5 > 52:
        raise ValueError("too many cards")
    rng = random.Random(seed)
    shares, attempts = [], 0
    while len(shares) < iterations and attempts < max_attempts:
        attempts += 1
        used = set(hero + board)
        hands = []
        valid = True
        for group in ranges:
            combo = group[rng.randrange(len(group))]
            if any(c in used for c in combo):
                valid = False
                break
            used.update(combo)
            hands.append(combo)
        if not valid:
            continue
        remaining = [c for c in DECK if c not in used]
        need = 5 - len(board)
        if len(remaining) < need:
            continue
        full_board = board + tuple(rng.sample(remaining, need))
        shares.append(showdown_shares([hero] + hands, full_board)[0])
    if len(shares) < iterations:
        raise ValueError("insufficient compatible samples for requested iterations")
    return {"shares": shares, "iterations": iterations, "seed": seed,
            "attempts": attempts, "opponents": len(ranges),
            "sampling_method": "independent_uniform_range_draws_reject_collisions",
            "range_uncertainty_included": False, "ocr_uncertainty_included": False,
            "gto_solution": False}
