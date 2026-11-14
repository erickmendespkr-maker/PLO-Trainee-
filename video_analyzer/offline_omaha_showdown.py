"""Offline PLO5/PLO6 showdown ranking: exactly two hole and three board cards.

Known complete hands only. No ranges, GTO, live assistance, rake or side pots.
"""
from collections import Counter
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "cdhs"

def _cards(cards, n):
    if not isinstance(cards, (list, tuple)) or len(cards) != n:
        raise ValueError("wrong card count")
    if any(not isinstance(c, str) or len(c) != 2 or c[0] not in RANKS or c[1] not in SUITS for c in cards):
        raise ValueError("invalid card")
    if len(set(cards)) != n:
        raise ValueError("duplicate card")
    return tuple(cards)

def _five(cards):
    ranks = [RANKS.index(c[0]) + 2 for c in cards]
    counts = Counter(ranks)
    distinct = set(ranks)
    if 14 in distinct:
        distinct.add(1)
    straight = next((t for t in range(14, 4, -1) if all(x in distinct for x in range(t-4, t+1))), 0)
    flush = len({c[1] for c in cards}) == 1
    groups = sorted(((n, r) for r, n in counts.items()), reverse=True)
    if flush and straight: return (8, straight)
    if groups[0][0] == 4: return (7, groups[0][1], groups[1][1])
    if groups[0][0] == 3 and groups[1][0] == 2: return (6, groups[0][1], groups[1][1])
    if flush: return (5, *sorted(ranks, reverse=True))
    if straight: return (4, straight)
    if groups[0][0] == 3: return (3, groups[0][1], *sorted((r for r in ranks if r != groups[0][1]), reverse=True))
    if groups[0][0] == 2 and groups[1][0] == 2:
        pairs = sorted((groups[0][1], groups[1][1]), reverse=True)
        return (2, *pairs, next(r for r in ranks if r not in pairs))
    if groups[0][0] == 2: return (1, groups[0][1], *sorted((r for r in ranks if r != groups[0][1]), reverse=True))
    return (0, *sorted(ranks, reverse=True))

def omaha_rank(hole, board):
    if not isinstance(hole, (list, tuple)) or len(hole) not in (5, 6):
        raise ValueError("requires PLO5 or PLO6")
    h, b = _cards(hole, len(hole)), _cards(board, 5)
    if len(set(h + b)) != len(h) + len(b):
        raise ValueError("overlapping cards")
    return max(_five(hh + bb) for hh in combinations(h, 2) for bb in combinations(b, 3))

def showdown_shares(hands, board):
    """Fractional showdown shares for complete known hands; no side pots."""
    if not isinstance(hands, (list, tuple)) or len(hands) < 2:
        raise ValueError("at least two hands required")
    b = _cards(board, 5)
    parsed = []
    for hand in hands:
        if not isinstance(hand, (list, tuple)) or len(hand) not in (5, 6):
            raise ValueError("requires PLO5 or PLO6")
        parsed.append(_cards(hand, len(hand)))
    all_cards = b + tuple(c for h in parsed for c in h)
    if len(set(all_cards)) != len(all_cards):
        raise ValueError("duplicate cards across hands")
    ranks = [omaha_rank(h, b) for h in parsed]
    best = max(ranks)
    winners = [i for i, rank in enumerate(ranks) if rank == best]
    return [1.0 / len(winners) if i in winners else 0.0 for i in range(len(hands))]
