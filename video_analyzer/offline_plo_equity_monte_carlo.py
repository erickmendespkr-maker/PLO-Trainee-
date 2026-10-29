"""Offline, single-opponent PLO5/PLO6 showdown equity from manually reviewed cards.

This module does NOT infer cards from video, determine hero actions, or offer live
poker assistance. Exactly two hole cards and three board cards form each hand.
95% confidence intervals describe Monte Carlo sampling error ONLY, not range,
OCR, player, or model uncertainty. Call EV is a terminal-showdown toy model.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from itertools import combinations
import json
import math
from pathlib import Path
import random

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK = tuple(r+s for r in RANKS for s in SUITS)
RANK_VALUE = {r: i+2 for i, r in enumerate(RANKS)}
MAX_JSON_BYTES = 2_000_000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON_BYTES,
            'invalid input file')
    def no_duplicates(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, 'duplicate JSON key')
            obj[k] = v
        return obj
    return json.loads(p.read_text('utf-8'), object_pairs_hook=no_duplicates,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def cards(value, count=None):
    require(type(value) is list and (count is None or len(value) == count), 'invalid card count')
    require(all(type(c) is str and len(c) == 2 and c[0] in RANKS and c[1] in SUITS for c in value),
            'invalid card syntax (use As, Td, 2c)')
    require(len(set(value)) == len(value), 'duplicate cards')
    return tuple(value)


def straight_high(values):
    ranks = set(values)
    if 14 in ranks:
        ranks.add(1)
    return next((high for high in range(14, 4, -1)
                 if all(v in ranks for v in range(high-4, high+1))), 0)


def five_rank(hand):
    """Comparable 5-card hand tuple, category 8..0, with correct wheel handling."""
    vals = [RANK_VALUE[c[0]] for c in hand]
    counts = Counter(vals)
    flush = len({c[1] for c in hand}) == 1
    straight = straight_high(vals)
    if flush and straight:
        return (8, straight)
    groups = sorted(((n, r) for r, n in counts.items()), reverse=True)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *sorted(vals, reverse=True))
    if straight:
        return (4, straight)
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((r for r, n in counts.items() if n == 1), reverse=True))
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    if len(pairs) == 2:
        return (2, *pairs, next(r for r, n in counts.items() if n == 1))
    if len(pairs) == 1:
        return (1, pairs[0], *sorted((r for r, n in counts.items() if n == 1), reverse=True))
    return (0, *sorted(vals, reverse=True))


def omaha_rank(hole, board):
    require(len(hole) in (5, 6) and len(board) == 5, 'Omaha requires 5/6 hole and 5 board cards')
    require(len(set(hole + board)) == len(hole) + 5, 'duplicate showdown cards')
    return max(five_rank(p + t) for p in combinations(hole, 2) for t in combinations(board, 3))


def _number(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1_000_000_000,
            f'invalid {name}')
    return float(value)


def analyze(data):
    require(type(data) is dict, 'input must be JSON object')
    allowed = {'variant', 'hero_cards', 'board_cards', 'opponent_model', 'iterations',
               'seed', 'manual_review_confirmed', 'pot_now', 'call_cost'}
    require(set(data) <= allowed, 'unexpected fields in input')
    require(data.get('manual_review_confirmed') is True,
            'manual review must be explicitly asserted; raw OCR cannot be analyzed')
    variant = data.get('variant')
    require(variant in ('PLO5', 'PLO6'), 'variant must be PLO5 or PLO6')
    n = 5 if variant == 'PLO5' else 6
    hero = cards(data.get('hero_cards'), n)
    board = cards(data.get('board_cards'))
    require(3 <= len(board) <= 5, 'requires flop, turn or river (3..5 board cards)')
    known = set(hero + board)
    require(len(known) == len(hero) + len(board), 'hero and board overlap')
    iterations = data.get('iterations')
    seed = data.get('seed')
    require(type(iterations) is int and 2 <= iterations <= 50_000, 'iterations must be 2..50000')
    require(type(seed) is int and 0 <= seed < 2**32, 'seed must be unsigned 32-bit integer')
    model = data.get('opponent_model')
    require(type(model) is dict and model.get('kind') in ('uniform', 'weighted_combos'),
            'explicit opponent model required')
    require(set(model) <= {'kind', 'combos'}, 'unexpected opponent model fields')
    available = tuple(c for c in DECK if c not in known)
    require(len(available) >= n + 5-len(board), 'not enough unknown cards')
    eligible, cumulative = [], []
    blocked = 0
    if model['kind'] == 'uniform':
        require('combos' not in model, 'uniform model must not include combos')
    else:
        combos = model.get('combos')
        require(type(combos) is list and 1 <= len(combos) <= 1000,
                'weighted range must have 1..1000 combos')
        seen = set()
        total = 0.0
        for item in combos:
            require(type(item) is dict and set(item) == {'cards', 'weight'},
                    'invalid weighted combo')
            opponent = cards(item['cards'], n)
            canonical = tuple(sorted(opponent))
            require(canonical not in seen, 'duplicate weighted combo')
            seen.add(canonical)
            weight = item['weight']
            require(type(weight) in (int, float) and math.isfinite(weight)
                    and 0 < weight <= 1_000_000, 'invalid combo weight')
            if known.intersection(opponent):
                blocked += 1
                continue
            total += float(weight)
            eligible.append(opponent)
            cumulative.append(total)
        require(eligible and math.isfinite(total), 'range has no legal combos')
    pot_present = 'pot_now' in data or 'call_cost' in data
    require(not pot_present or ('pot_now' in data and 'call_cost' in data),
            'pot_now and call_cost must be provided together')
    if pot_present:
        pot = _number(data['pot_now'], 'pot_now')
        call = _number(data['call_cost'], 'call_cost')
    rng = random.Random(seed)
    wins = ties = losses = 0
    for _ in range(iterations):
        if model['kind'] == 'uniform':
            draw = rng.sample(available, n + 5-len(board))
            opponent, runout = tuple(draw[:n]), tuple(draw[n:])
        else:
            idx = bisect_left(cumulative, rng.random()*cumulative[-1])
            opponent = eligible[min(idx, len(eligible)-1)]
            pool = tuple(c for c in available if c not in opponent)
            runout = tuple(rng.sample(pool, 5-len(board)))
        full_board = board + runout
        ours = omaha_rank(hero, full_board)
        theirs = omaha_rank(opponent, full_board)
        wins += ours > theirs
        ties += ours == theirs
        losses += ours < theirs
    equity = (wins + ties/2)/iterations
    # Bernoulli-like sample shares 1, 1/2, 0; sample variance (unbiased).
    second_moment = (wins + ties/4)/iterations
    sample_variance = max(0., (second_moment - equity**2)*iterations/(iterations-1))
    se = math.sqrt(sample_variance/iterations)
    low, high = max(0., equity-1.96*se), min(1., equity+1.96*se)
    result = {
        'schema_version': 1, 'analysis_status': 'offline_manual_assumptions_monte_carlo_only',
        'variant': variant, 'hero_cards': list(hero), 'board_cards': list(board),
        'opponent_model_kind': model['kind'],
        'range_eligible_combos': len(eligible) if eligible else None,
        'range_blocked_combos': blocked if model['kind'] == 'weighted_combos' else None,
        'iterations': iterations, 'seed': seed,
        'win_count': wins, 'tie_count': ties, 'loss_count': losses,
        'win_rate': wins/iterations, 'tie_rate': ties/iterations, 'loss_rate': losses/iterations,
        'equity': equity, 'equity_ci95_sampling_only': [low, high],
        'sampling_standard_error': se,
        'exactly_two_hole_three_board_rule': True,
        'manual_review_claimed_not_independently_verified': True,
        'ocr_semantics_verified': False, 'player_identity_verified': False,
        'range_accuracy_verified': False, 'strategic_correctness_verified': False,
        'warning': ('95% interval reflects simulation sampling only; it does not cover '
                    'range assumptions, OCR errors, player identity, or future betting.')
    }
    if pot_present:
        # pot_now already includes any opponent bet, BEFORE hero's call.
        # Final pot if called = pot_now + call; incremental fold EV = 0.
        final_pot = pot + call
        result['terminal_call_ev_model'] = {
            'pot_now_including_opponent_bet': pot, 'hero_call_cost': call,
            'fold_ev_incremental': 0.0,
            'call_ev_incremental': equity*final_pot-call,
            'call_ev_ci95_sampling_only': [low*final_pot-call, high*final_pot-call],
            'assumptions': ('heads-up, no rake, no side pots, no further betting, '
                            'equity showdown realization, fixed opponent range'),
            'raise_ev': None,
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_input_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    out = Path(args.new_output_json)
    require(out.parent.is_dir() and not out.parent.is_symlink() and not out.exists()
            and not out.is_symlink() and out.suffix == '.json', 'output must be a new JSON file')
    source = Path(args.reviewed_input_json)
    require(source.resolve() != out.resolve(), 'cannot overwrite input')
    result = analyze(read_json(source))
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({'equity': result['equity'], 'iterations': result['iterations'],
                      'analysis_status': result['analysis_status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
