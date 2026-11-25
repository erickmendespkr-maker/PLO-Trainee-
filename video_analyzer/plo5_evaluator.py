"""Strict offline PLO5 high-hand ranking and conditional showdown shares."""
from fractions import Fraction
from itertools import combinations

if __package__:
    from .offline_omaha_showdown import _cards
    from .plo5_rank_cache import fast_five as _five
else:
    from offline_omaha_showdown import _cards
    from plo5_rank_cache import fast_five as _five

CATEGORIES = ('high_card', 'one_pair', 'two_pair', 'three_of_a_kind',
              'straight', 'flush', 'full_house', 'four_of_a_kind', 'straight_flush')


def evaluate(hole, board):
    """Best *current* made hand (flop/turn/river); not future equity or GTO."""
    h = _cards(hole, 5)
    if not isinstance(board, (list, tuple)) or len(board) not in (3, 4, 5):
        raise ValueError('PLO5 evaluation requires 3, 4 or 5 board cards')
    b = _cards(board, len(board))
    if len(set(h + b)) != len(h) + len(b):
        raise ValueError('Private and community cards overlap')
    best = None
    witness = None
    count = 0
    for two in combinations(sorted(h), 2):
        for three in combinations(sorted(b), 3):
            rank = _five(two + three)
            count += 1
            if best is None or rank > best:
                best, witness = rank, (two, three)
    return {'rank': best, 'category': CATEGORIES[best[0]],
            'used_private': witness[0], 'used_board': witness[1],
            'combinations_evaluated': count, 'board_count': len(b),
            'variant': 5, 'gto_solution': False, 'video_verified': False}


def showdown(hands, board):
    """Known complete eligible holdings; equal pot shares, no side pots or rake."""
    if not isinstance(hands, (list, tuple)) or not 2 <= len(hands) <= 6:
        raise ValueError('Expected 2–6 PLO5 holdings')
    b = _cards(board, 5)
    parsed = [_cards(h, 5) for h in hands]
    all_cards = b + tuple(c for h in parsed for c in h)
    if len(set(all_cards)) != len(all_cards):
        raise ValueError('Duplicate cards across holdings and board')
    ranks = [evaluate(h, b)['rank'] for h in parsed]
    winners = [i for i, rank in enumerate(ranks) if rank == max(ranks)]
    shares = [Fraction(1, len(winners)) if i in winners else Fraction(0) for i in range(len(parsed))]
    return {'variant': 5, 'ranks': ranks, 'winner_indices': winners,
            'shares': [{'numerator': s.numerator, 'denominator': s.denominator} for s in shares],
            'method': 'known_holdings_equal_eligible_pot_shares',
            'side_pots_modeled': False, 'rake_modeled': False,
            'video_verified': False, 'gto_solution': False}
