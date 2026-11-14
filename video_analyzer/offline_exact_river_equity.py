"""Exact conditional river equity for a single PLO5/PLO6 opponent range.

Each listed opponent combination is equally weighted, after blockers. This is
not a solver, an inference about a real opponent, or video verification.
"""
from .offline_omaha_showdown import _cards, showdown_shares


def exact_river_equity(*, hero, board, opponent_range):
    if not isinstance(hero, (tuple, list)) or len(hero) not in (5, 6):
        raise ValueError("hero must have five or six cards")
    hero = _cards(hero, len(hero))
    board = _cards(board, 5)
    if len(set(hero + board)) != len(hero) + 5:
        raise ValueError("hero and board overlap")
    if not isinstance(opponent_range, (tuple, list)) or not opponent_range:
        raise ValueError("nonempty opponent range required")
    seen, legal = set(), []
    blockers = set(hero + board)
    for hand in opponent_range:
        combo = _cards(hand, len(hero))
        key = tuple(sorted(combo))
        if key in seen:
            raise ValueError("duplicate opponent combo, including reordered cards")
        seen.add(key)
        if not blockers.intersection(combo):
            legal.append(combo)
    if not legal:
        raise ValueError("no opponent combos survive blockers")
    shares = [showdown_shares([hero, hand], board)[0] for hand in legal]
    wins = sum(share == 1.0 for share in shares)
    ties = sum(share == 0.5 for share in shares)
    return {"equity": sum(shares) / len(shares), "wins": wins,
            "ties": ties, "losses": len(shares) - wins - ties,
            "legal_combos": len(legal), "excluded_by_blockers": len(opponent_range) - len(legal),
            "method": "exact_uniform_legal_opponent_combos_river_heads_up",
            "range_uncertainty_included": False, "ocr_verified": False,
            "video_hand_verified": False, "gto_solution": False}
