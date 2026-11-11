"""Offline weighted PLO5/PLO6 equity; user-supplied range hypotheses, never GTO."""
from __future__ import annotations
import math
import random
from offline_omaha_equity import DECK, CARD, validate, omaha_rank


def prepare(hero, board, entries):
    if type(hero) is not list or len(hero) not in (5, 6) or type(board) is not list or len(board) not in (0, 3, 4, 5):
        raise ValueError('expected PLO5/PLO6 hero and 0/3/4/5 board')
    known = hero + board
    if any(type(c) is not str or not CARD.fullmatch(c) for c in known) or len(set(known)) != len(known):
        raise ValueError('invalid or duplicate known cards')
    if type(entries) is not list or not 1 <= len(entries) <= 10000:
        raise ValueError('nonempty bounded range required')
    accepted, rejected, total = [], 0., 0.
    seen = set()
    for item in entries:
        if type(item) is not dict or set(item) != {'cards', 'weight'}:
            raise ValueError('range entry must contain cards and weight')
        cards, weight = item['cards'], item['weight']
        if type(cards) is not list or len(cards) != len(hero) or any(type(c) is not str or not CARD.fullmatch(c) for c in cards) or len(set(cards)) != len(cards):
            raise ValueError('invalid range holding')
        if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0 or weight > 1e12:
            raise ValueError('invalid range weight')
        canonical = tuple(sorted(cards))
        if canonical in seen:
            raise ValueError('duplicate range holding (order ignored)')
        seen.add(canonical)
        total += weight
        if set(cards).isdisjoint(known):
            validate(hero, cards, board)
            accepted.append((cards, weight))
        else:
            rejected += weight
    remaining = sum(w for _, w in accepted)
    if not remaining or not math.isfinite(total):
        raise ValueError('all range weight blocked or total weight overflow')
    return accepted, {'original_entries': len(entries), 'accepted_entries': len(accepted),
                      'blocked_entries': len(entries) - len(accepted),
                      'blocked_weight_fraction': rejected / total,
                      'accepted_weight_fraction': remaining / total,
                      'weights_renormalized_after_blockers': True}


def equity(hero, board, entries, iterations=10000, seed=0):
    if type(iterations) is not int or not 1 <= iterations <= 1000000 or type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise ValueError('invalid iterations or seed')
    accepted, audit = prepare(hero, board, entries)
    rng = random.Random(seed)
    weights = [w for _, w in accepted]
    wins = ties = 0
    for idx in rng.choices(range(len(accepted)), weights=weights, k=iterations):
        villain = accepted[idx][0]
        used = set(hero + board + villain)
        remaining = [c for c in DECK if c not in used]
        runout = rng.sample(remaining, 5-len(board))
        final_board = board + runout
        a, b = omaha_rank(hero, final_board), omaha_rank(villain, final_board)
        wins += a > b
        ties += a == b
    q = (wins + ties / 2) / iterations
    half = math.sqrt(math.log(40)/(2*iterations))
    return {'method': 'weighted_range_monte_carlo', 'seed': seed, 'trials': iterations,
            'wins': wins, 'ties': ties, 'losses': iterations-wins-ties,
            'equity': q, 'ci95_conservative': [max(0, q-half), min(1, q+half)],
            'ci_method': 'Hoeffding bounded payoff, iid weighted holding and board draws',
            'range_audit': audit, 'range_is_user_assumption': True,
            'range_uncertainty_included_in_ci': False, 'gto_solution': False,
            'opponent_holding_known_assumed': False}


def exact_river(hero, board, entries):
    if type(board) is not list or len(board) != 5:
        raise ValueError('exact weighted enumeration requires full river board')
    accepted, audit = prepare(hero, board, entries)
    total = sum(w for _, w in accepted)
    a = omaha_rank(hero, board)
    wins = ties = 0.
    for villain, weight in accepted:
        b = omaha_rank(villain, board)
        wins += weight * (a > b)
        ties += weight * (a == b)
    return {'method': 'exact_weighted_river', 'equity': (wins + ties/2)/total,
            'range_audit': audit, 'range_is_user_assumption': True,
            'range_uncertainty_included_in_ci': False, 'gto_solution': False}
