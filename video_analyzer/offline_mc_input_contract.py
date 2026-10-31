"""Fail-closed, offline validation of *independently entered* PLO5/PLO6 equity scenarios.

No OCR/visual-review ledger is promoted into mathematical truth. This module
validates an explicit scenario; it does not calculate equity, EV, or decisions.
Usage: python offline_mc_input_contract.py SUMMARY.json SCENARIO.json NEW_OUTPUT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

SHA = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')
STREETS = {3: 'flop', 4: 'turn', 5: 'river'}
MAX_FILE_BYTES = 2_000_000


def check(ok, message):
    if not ok:
        raise ValueError(message)


def no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        check(key not in obj, 'duplicate JSON key')
        obj[key] = value
    return obj


def bad_constant(value):
    raise ValueError('nonfinite JSON number')


def read_json(path):
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE_BYTES,
          'invalid or oversized input file')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates,
                      parse_constant=bad_constant)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def cards(value, count, label):
    check(type(value) is list and len(value) == count, f'{label}: wrong number of cards')
    check(all(type(c) is str and CARD.fullmatch(c) for c in value), f'{label}: invalid card')
    check(len(set(value)) == len(value), f'{label}: duplicate cards')
    return tuple(value)


def positive_money(value, label, allow_zero=False):
    check(type(value) in (int, float) and math.isfinite(value) and
          (value >= 0 if allow_zero else value > 0) and value <= 1_000_000_000,
          f'{label}: invalid amount')
    return value


def feasible_joint_assignment(ranges, used):
    """Check that at least one non-colliding set of opponent hands exists."""
    def visit(i, occupied):
        if i == len(ranges):
            return True
        for entry in ranges[i]:
            hand = set(entry['cards'])
            if not (hand & occupied) and visit(i + 1, occupied | hand):
                return True
        return False
    return visit(0, set(used))


def build(summary, scenario, summary_sha):
    check(type(summary_sha) is str and SHA.fullmatch(summary_sha), 'invalid summary SHA')
    check(type(summary) is dict and summary.get('schema_version') == 1 and
          summary.get('status') == 'offline_hand_visual_summary_unverified_not_math_ready' and
          type(summary.get('eligible_for_equity')) is int and summary['eligible_for_equity'] == 0 and
          summary.get('equity_or_ev_calculated') is False and
          summary.get('reviewer_claims_not_authenticated') is True and
          summary.get('video_content_not_semantically_verified') is True and
          type(summary.get('hands')) is list and 1 <= len(summary['hands']) <= 100 and
          type(summary.get('hand_count')) is int and summary['hand_count'] == len(summary['hands']) and
          type(summary.get('source_video_sha256_claim')) is str and
          SHA.fullmatch(summary['source_video_sha256_claim']), 'invalid unverified summary')
    check(type(scenario) is dict and set(scenario) == {
        'schema_version', 'hand_id', 'table_id', 'source_summary_sha256',
        'source_video_sha256_claim', 'input_origin', 'variant', 'hero_cards',
        'board_cards', 'opponents', 'pot_before_call', 'to_call',
        'effective_stack', 'seed', 'simulations', 'assumptions',
        'future_action_model'}, 'invalid scenario schema')
    check(type(scenario['schema_version']) is int and scenario['schema_version'] == 1,
          'invalid scenario version')
    for key in ('hand_id', 'table_id'):
        check(type(scenario[key]) is str and ID.fullmatch(scenario[key]), f'invalid {key}')
    check(scenario['source_summary_sha256'] == summary_sha and
          scenario['source_video_sha256_claim'] == summary['source_video_sha256_claim'],
          'source provenance mismatch')
    matches = [h for h in summary['hands'] if type(h) is dict and
               h.get('hand_id') == scenario['hand_id'] and
               h.get('table_id') == scenario['table_id']]
    check(len(matches) == 1 and matches[0].get('math_ready') is False and
          matches[0].get('eligible_for_equity') is False,
          'hand not uniquely linked to unverified summary')
    check(scenario['input_origin'] == 'independent_manual_transcription',
          'OCR/reviewer claims cannot be promoted to manual input')
    variant = scenario['variant']
    check(type(variant) is str and variant in ('PLO5', 'PLO6'), 'invalid variant')
    n = int(variant[-1])
    hero = cards(scenario['hero_cards'], n, 'hero')
    board_value = scenario['board_cards']
    check(type(board_value) is list and len(board_value) in STREETS, 'board must have 3-5 cards')
    board = cards(board_value, len(board_value), 'board')
    used = set(hero + board)
    check(len(used) == len(hero) + len(board), 'hero/board collision')
    opponents = scenario['opponents']
    check(type(opponents) is list and 1 <= len(opponents) <= 3, '1-3 opponents required')
    normalized = []
    for idx, opponent in enumerate(opponents):
        check(type(opponent) is dict and set(opponent) == {'range_name', 'combos'},
              'invalid opponent range schema')
        name = opponent['range_name']
        check(type(name) is str and ID.fullmatch(name), 'invalid range name')
        entries = opponent['combos']
        check(type(entries) is list and 1 <= len(entries) <= 100,
              'range must contain 1-100 explicit combos')
        seen = set()
        combos = []
        total = 0.0
        for item in entries:
            check(type(item) is dict and set(item) == {'cards', 'weight'},
                  'invalid range combo schema')
            hand = cards(item['cards'], n, f'opponent {idx + 1}')
            check(not (set(hand) & used), 'opponent range collides with known cards')
            identity = tuple(sorted(hand))
            check(identity not in seen, 'duplicate unordered opponent combo')
            seen.add(identity)
            weight = item['weight']
            check(type(weight) in (int, float) and math.isfinite(weight) and
                  0 < weight <= 1_000_000, 'invalid combo weight')
            total += weight
            check(math.isfinite(total), 'invalid total weight')
            combos.append({'cards': list(hand), 'weight': weight})
        normalized.append({'range_name': name, 'combos': combos,
                           'total_input_weight': total})
    check(feasible_joint_assignment([r['combos'] for r in normalized], used),
          'no feasible disjoint opponent assignment')
    pot = positive_money(scenario['pot_before_call'], 'pot')
    to_call = positive_money(scenario['to_call'], 'to_call', allow_zero=True)
    stack = positive_money(scenario['effective_stack'], 'effective_stack')
    check(to_call <= stack, 'to_call exceeds effective_stack')
    check(type(scenario['seed']) is int and 0 <= scenario['seed'] <= 2**32 - 1,
          'invalid deterministic seed')
    check(type(scenario['simulations']) is int and
          1000 <= scenario['simulations'] <= 2_000_000, 'invalid simulation count')
    check(type(scenario['assumptions']) is str and
          20 <= len(scenario['assumptions'].strip()) <= 2000,
          'explicit assumptions required')
    check(scenario['future_action_model'] == 'showdown_equity_only',
          'unsupported future action model; EV is not calculated')
    return {
        'schema_version': 1,
        'status': 'manual_scenario_validated_not_executed',
        'hand_id': scenario['hand_id'], 'table_id': scenario['table_id'],
        'source_summary_sha256': summary_sha,
        'source_video_sha256_claim': summary['source_video_sha256_claim'],
        'manual_input_origin_claim_not_authenticated': True,
        'summary_review_not_promoted_to_fact': True,
        'variant': variant, 'hero_cards': list(hero), 'board_cards': list(board),
        'street': STREETS[len(board)], 'opponents': normalized,
        'pot_before_call': pot, 'to_call': to_call, 'effective_stack': stack,
        'seed': scenario['seed'], 'simulations': scenario['simulations'],
        'assumptions': scenario['assumptions'].strip(),
        'omaha_rule': 'exactly_two_hole_and_three_board',
        'future_action_model': 'showdown_equity_only',
        'equity_calculated': False, 'ev_calculated': False,
        'confidence_interval_calculated': False,
        'automatic_ocr_math_authorization': False,
        'warning': 'Manual values and ranges are unverified assumptions; this file is a validated input candidate, not equity, EV or a poker verdict.'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary_json')
    parser.add_argument('scenario_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    a, b, target = map(Path, (args.summary_json, args.scenario_json, args.new_output_json))
    check(a.resolve() != b.resolve() and target.suffix == '.json' and
          target.parent.is_dir() and not target.parent.is_symlink() and
          not target.exists() and not target.is_symlink() and
          target.resolve() not in (a.resolve(), b.resolve()), 'output must be new and distinct')
    digests = (sha256(a), sha256(b))
    result = build(read_json(a), read_json(b), digests[0])
    check(digests == (sha256(a), sha256(b)), 'input changed during validation')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'hand_id': result['hand_id'],
                      'equity_calculated': False, 'ev_calculated': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
