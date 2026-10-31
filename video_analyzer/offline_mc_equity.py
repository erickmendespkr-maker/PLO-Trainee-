"""Offline, deterministic *conditional* PLO5/PLO6 Monte Carlo equity.

Only independently entered, revalidated scenarios are accepted. Opponent combos
are sampled jointly proportional to the product of explicit range weights,
conditioned on no card collisions. Future board cards are sampled uniformly
without replacement. Exactly two hole and three board cards must play.

This computes showdown equity under specified ranges, NOT action EV or a verdict.
Usage: python offline_mc_equity.py SUMMARY.json SCENARIO.json NEW_RESULT.json
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from functools import lru_cache
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import random

import offline_mc_input_contract as contract

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK = tuple(r + s for r in RANKS for s in SUITS)
CARD_INDEX = {c: i for i, c in enumerate(DECK)}
MAX_ASSIGNMENTS = 100_000  # guard against combinatorial blowup
MAX_TRIALS = 50_000  # bounded offline proof-of-concept; contract allows more


def mask(cards):
    result = 0
    for c in cards:
        result |= 1 << CARD_INDEX[c]
    return result


@lru_cache(maxsize=100_000)
def five_card_rank(hand):
    """Standard high-hand order; tuple comparison is lexicographic."""
    values = sorted((RANKS.index(c[0]) + 2 for c in hand), reverse=True)
    from collections import Counter
    counts = Counter(values)
    groups = sorted(((n, v) for v, n in counts.items()), reverse=True)
    flush = len({c[1] for c in hand}) == 1
    distinct = set(values)
    if 14 in distinct:
        distinct.add(1)
    straight = max((hi for hi in range(5, 15)
                    if all(hi - d in distinct for d in range(5))), default=0)
    if straight and flush:
        return (8, straight)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *values)
    if straight:
        return (4, straight)
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((v for v in values if v != groups[0][1]), reverse=True))
    if groups[0][0] == 2 and groups[1][0] == 2:
        pairs = sorted((groups[0][1], groups[1][1]), reverse=True)
        return (2, *pairs, next(v for v in values if v not in pairs))
    if groups[0][0] == 2:
        return (1, groups[0][1], *sorted((v for v in values if v != groups[0][1]), reverse=True))
    return (0, *values)


def omaha_rank(hole, board):
    if len(board) != 5 or len(hole) not in (5, 6):
        raise ValueError('Omaha requires five board and five/six hole cards')
    return max(five_card_rank(tuple(sorted(h + b)))
               for h in combinations(hole, 2)
               for b in combinations(board, 3))


def joint_range_sampler(validated):
    """Build exact conditional distribution over feasible joint combos.

    Reject too many feasible combinations rather than silently biasing ranges.
    """
    occupied = mask(validated['hero_cards'] + validated['board_cards'])
    opponent_ranges = validated['opponents']
    cumulative = []
    assignments = []
    total = 0.0
    examined = 0

    def walk(i, used, selected, weight):
        nonlocal total, examined
        if i == len(opponent_ranges):
            examined += 1
            if examined > MAX_ASSIGNMENTS:
                raise ValueError('too many feasible joint range assignments')
            total += weight
            if not math.isfinite(total):
                raise ValueError('joint range weight overflow')
            cumulative.append(total)
            assignments.append(tuple(selected))
            return
        for entry in opponent_ranges[i]['combos']:
            cards = tuple(entry['cards'])
            bits = mask(cards)
            if not bits & used:
                walk(i + 1, used | bits, selected + [cards], weight * entry['weight'])

    walk(0, occupied, [], 1.0)
    if not assignments or total <= 0:
        raise ValueError('no feasible joint opponent assignment')

    def sample(rng):
        pos = bisect_left(cumulative, rng.random() * total)
        return assignments[min(pos, len(assignments) - 1)]

    return sample, len(assignments)


def compute(validated):
    if (type(validated) is not dict or
        validated.get('status') != 'manual_scenario_validated_not_executed' or
        validated.get('equity_calculated') is not False or
        validated.get('ev_calculated') is not False or
        validated.get('automatic_ocr_math_authorization') is not False or
        validated.get('manual_input_origin_claim_not_authenticated') is not True or
        validated.get('future_action_model') != 'showdown_equity_only' or
        validated.get('omaha_rule') != 'exactly_two_hole_and_three_board'):
        raise ValueError('scenario not independently validated')
    hero = tuple(validated['hero_cards'])
    board = tuple(validated['board_cards'])
    n = validated['simulations']
    if type(n) is not int or not 1000 <= n <= MAX_TRIALS:
        raise ValueError('invalid simulation count')
    seed = validated['seed']
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('invalid seed')
    if len(hero) != int(validated['variant'][-1]) or len(board) not in (3, 4, 5):
        raise ValueError('invalid card counts')
    sampler, assignment_count = joint_range_sampler(validated)
    rng = random.Random(seed)
    hero_mask = mask(hero + board)
    sum_share = sum_sq = 0.0
    wins = ties = losses = 0
    for _ in range(n):
        opponents = sampler(rng)
        occupied = hero_mask
        for hole in opponents:
            occupied |= mask(hole)
        remaining = [c for c in DECK if not (occupied & (1 << CARD_INDEX[c]))]
        runout = rng.sample(remaining, 5 - len(board))
        full_board = board + tuple(runout)
        hero_score = omaha_rank(hero, full_board)
        opp_scores = [omaha_rank(h, full_board) for h in opponents]
        best = max([hero_score] + opp_scores)
        if hero_score == best:
            winners = 1 + sum(score == best for score in opp_scores)
            share = 1.0 / winners
            if winners == 1:
                wins += 1
            else:
                ties += 1
        else:
            share = 0.0
            losses += 1
        sum_share += share
        sum_sq += share * share
    equity = sum_share / n
    # Approximate normal CI on per-trial pot share, not binomial when ties occur.
    variance = max(0.0, (sum_sq - n * equity * equity) / (n - 1))
    margin = 1.959963984540054 * math.sqrt(variance / n)
    return {
        'schema_version': 1,
        'status': 'conditional_showdown_equity_estimated_not_ev',
        'hand_id': validated['hand_id'], 'table_id': validated['table_id'],
        'variant': validated['variant'], 'street': validated['street'],
        'source_summary_sha256': validated['source_summary_sha256'],
        'source_video_sha256_claim': validated['source_video_sha256_claim'],
        'input_origin_claim': 'independent_manual_transcription_not_authenticated',
        'assumptions': validated['assumptions'],
        'range_names': [o['range_name'] for o in validated['opponents']],
        'joint_feasible_range_assignments': assignment_count,
        'joint_sampling': 'product_of_input_weights_conditioned_on_disjoint_hands',
        'future_board_sampling': 'uniform_without_replacement_after_opponent_assignment',
        'omaha_rule': 'exactly_two_hole_and_three_board',
        'seed': seed, 'simulations': n,
        'hero_win_count': wins, 'hero_tie_count': ties, 'hero_loss_count': losses,
        'equity_fraction': equity,
        'confidence_interval_95_approx': [max(0.0, equity - margin), min(1.0, equity + margin)],
        'confidence_method': 'normal_approximation_on_independent_pot_shares_not_range_uncertainty',
        'equity_calculated': True, 'ev_calculated': False,
        'fold_call_raise_ev': None,
        'automatic_ocr_math_authorization': False,
        'warning': 'Conditional showdown equity only. Manually entered cards/ranges are unverified; interval excludes range/model/visual uncertainty. No action EV or error verdict.'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary_json')
    parser.add_argument('scenario_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    a, b, target = map(Path, (args.summary_json, args.scenario_json, args.new_output_json))
    contract.check(a.resolve() != b.resolve() and target.suffix == '.json' and
                   target.parent.is_dir() and not target.parent.is_symlink() and
                   not target.exists() and not target.is_symlink() and
                   target.resolve() not in (a.resolve(), b.resolve()),
                   'output must be new and distinct')
    before = (contract.sha256(a), contract.sha256(b))
    validated = contract.build(contract.read_json(a), contract.read_json(b), before[0])
    result = compute(validated)
    contract.check(before == (contract.sha256(a), contract.sha256(b)),
                   'input changed during Monte Carlo')
    result['source_scenario_sha256'] = before[1]
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'equity_fraction': result['equity_fraction'],
                      'simulations': result['simulations'], 'ev_calculated': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
