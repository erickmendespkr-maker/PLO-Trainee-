"""Offline, fail-closed bridge from human-reviewed clip plans to PLO equity inputs.

Usage: python offline_reviewed_hand_math_queue.py PLAN.json CARDS.json NEW_QUEUE.json

Only human-confirmed cards with per-card, in-clip frame timestamps become eligible
for the *existing* Monte Carlo engine. No video is read and no equity is computed.
Frame timestamps, cards and confidence are reviewer assertions, not verified OCR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

ID = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
RANKS, SUITS = '23456789TJQKA', 'cdhs'
MAX_INPUT = 4_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(x, minimum=0, maximum=1e9):
    return type(x) in (int, float) and math.isfinite(x) and minimum <= x <= maximum


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_INPUT,
            'invalid or oversized input file')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    result = json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    require(type(result) is dict, 'JSON root must be an object')
    return result


def card_list(value, count_min, count_max):
    require(type(value) is list and count_min <= len(value) <= count_max and
            all(type(c) is str and len(c) == 2 and c[0] in RANKS and c[1] in SUITS
                for c in value) and len(set(value)) == len(value), 'invalid cards')
    return value


def validate_plan(plan):
    require(type(plan) is dict and plan.get('schema_version') == 1 and
            plan.get('status') == 'human_reviewed_clip_plan_not_automated_hand_detection' and
            type(plan.get('source_video_sha256')) is str and
            SHA.fullmatch(plan['source_video_sha256']) and
            type(plan.get('clips')) is list and 1 <= len(plan['clips']) <= 100 and
            plan.get('equity_or_ev_calculated') is False,
            'unsupported reviewed clip plan')
    clips = {}
    for clip in plan['clips']:
        require(type(clip) is dict and type(clip.get('hand_id')) is str and
                ID.fullmatch(clip['hand_id']) and clip['hand_id'] not in clips and
                type(clip.get('table_id')) is str and ID.fullmatch(clip['table_id']) and
                clip.get('review_basis') == 'human_declared_boundaries_not_automatic_detection' and
                number(clip.get('start_seconds'), 0, 14400) and
                number(clip.get('end_seconds'), 0, 14400) and
                .1 <= clip['end_seconds']-clip['start_seconds'] <= 300,
                'invalid or duplicated reviewed clip')
        clips[clip['hand_id']] = clip
    require(len({c['table_id'] for c in clips.values()}) <= 4, 'more than four tables')
    return clips


def validate_range(model, n, known):
    require(type(model) is dict and model.get('kind') in ('uniform', 'weighted_combos') and
            set(model) <= {'kind', 'combos'}, 'invalid opponent model')
    if model['kind'] == 'uniform':
        require('combos' not in model, 'uniform range cannot include combos')
        return True
    combos = model.get('combos')
    require(type(combos) is list and 1 <= len(combos) <= 1000,
            'weighted range requires 1..1000 combos')
    seen, legal = set(), False
    for combo in combos:
        require(type(combo) is dict and set(combo) == {'cards', 'weight'} and
                number(combo['weight'], 0, 1e6) and combo['weight'] > 0,
                'invalid range combo or weight')
        cards = card_list(combo['cards'], n, n)
        key = tuple(sorted(cards))
        require(key not in seen, 'duplicate range combo')
        seen.add(key)
        legal |= not bool(known.intersection(cards))
    return legal


def build(plan, annotations, plan_sha, annotations_sha):
    clips = validate_plan(plan)
    require(type(plan_sha) is str and SHA.fullmatch(plan_sha) and
            type(annotations_sha) is str and SHA.fullmatch(annotations_sha) and
            type(annotations) is dict and set(annotations) ==
            {'schema_version', 'source_plan_sha256', 'hands'} and
            annotations['schema_version'] == 1 and
            annotations['source_plan_sha256'] == plan_sha and
            type(annotations['hands']) is list and len(annotations['hands']) <= len(clips),
            'invalid or unbound manual card annotations')
    by_hand = {}
    allowed = {'hand_id', 'table_id', 'variant', 'card_review_status', 'hero_cards',
               'board_cards', 'card_evidence', 'opponent_model', 'iterations', 'seed',
               'pot_now', 'call_cost', 'reviewer_confidence_declared'}
    for item in annotations['hands']:
        require(type(item) is dict and set(item) <= allowed and
                type(item.get('hand_id')) is str and item['hand_id'] in clips and
                item['hand_id'] not in by_hand and
                item.get('table_id') == clips[item['hand_id']]['table_id'],
                'unknown, duplicated or cross-table annotation')
        by_hand[item['hand_id']] = item
    entries = []
    for hand_id, clip in clips.items():
        entry = {'hand_id': hand_id, 'table_id': clip['table_id'],
                 'start_seconds': clip['start_seconds'],
                 'end_seconds': clip['end_seconds'],
                 'eligible_for_offline_monte_carlo': False,
                 'equity_input': None, 'blocked_reasons': [],
                 'reviewer_confidence_declared_not_calibrated': None}
        item = by_hand.get(hand_id)
        reasons = entry['blocked_reasons']
        if item is None:
            reasons.append('no_human_annotation')
            entries.append(entry)
            continue
        conf = item.get('reviewer_confidence_declared')
        if conf is not None:
            require(number(conf, 0, 1), 'invalid reviewer confidence')
            entry['reviewer_confidence_declared_not_calibrated'] = conf
        if item.get('card_review_status') != 'human_confirmed':
            require(item.get('card_review_status') in ('ocr_unverified', 'unknown'),
                    'invalid card review status')
            reasons.append('cards_not_human_confirmed')
        variant = item.get('variant')
        if variant not in ('PLO5', 'PLO6'):
            reasons.append('variant_missing')
        n = 5 if variant == 'PLO5' else 6 if variant == 'PLO6' else None
        hero, board = item.get('hero_cards'), item.get('board_cards')
        if n is None or hero is None or board is None:
            reasons.append('incomplete_cards')
            known = None
        else:
            card_list(hero, n, n)
            card_list(board, 3, 5)
            require(not set(hero).intersection(board), 'hero/board card collision')
            known = set(hero + board)
        evidence = item.get('card_evidence')
        if known is None or type(evidence) is not list or len(evidence) != len(known):
            reasons.append('missing_per_card_frame_evidence')
        else:
            evidence_cards = []
            for row in evidence:
                require(type(row) is dict and set(row) ==
                        {'card', 'pts_seconds', 'source'} and
                        row.get('source') == 'human_frame_review' and
                        type(row.get('card')) is str and
                        number(row.get('pts_seconds'), clip['start_seconds'],
                               clip['end_seconds']), 'invalid frame evidence')
                evidence_cards.append(row['card'])
            require(len(set(evidence_cards)) == len(evidence_cards),
                    'duplicate card frame evidence')
            if set(evidence_cards) != known:
                reasons.append('card_evidence_mismatch')
        model = item.get('opponent_model')
        if model is None:
            reasons.append('opponent_range_not_supplied')
        elif known is not None and not validate_range(model, n, known):
            reasons.append('opponent_range_fully_blocked')
        elif known is None:
            reasons.append('opponent_range_cannot_be_checked')
        iterations, seed = item.get('iterations'), item.get('seed')
        if type(iterations) is not int or not 2 <= iterations <= 50000 or\
           type(seed) is not int or not 0 <= seed < 2**32:
            reasons.append('missing_valid_simulation_parameters')
        pot_present = 'pot_now' in item or 'call_cost' in item
        if pot_present:
            require('pot_now' in item and 'call_cost' in item and
                    number(item['pot_now']) and number(item['call_cost']),
                    'invalid terminal call EV inputs')
        if not reasons:
            equity = {'variant': variant, 'hero_cards': hero, 'board_cards': board,
                      'opponent_model': model, 'iterations': iterations,
                      'seed': seed, 'manual_review_confirmed': True}
            if pot_present:
                equity.update(pot_now=item['pot_now'], call_cost=item['call_cost'])
            entry['equity_input'] = equity
            entry['eligible_for_offline_monte_carlo'] = True
        entries.append(entry)
    return {'schema_version': 1,
            'status': 'offline_human_reviewed_math_inputs_not_executed',
            'source_video_sha256_claim': plan['source_video_sha256'],
            'source_plan_sha256': plan_sha,
            'source_annotations_sha256': annotations_sha,
            'entries': entries,
            'eligible_count': sum(x['eligible_for_offline_monte_carlo'] for x in entries),
            'blocked_count': sum(not x['eligible_for_offline_monte_carlo'] for x in entries),
            'equity_or_ev_calculated': False,
            'ocr_semantics_verified': False,
            'video_card_visibility_machine_verified': False,
            'reviewed_cards_are_human_assertions': True,
            'opponent_ranges_are_assumptions': True,
            'reviewer_confidence_is_not_statistical_confidence': True,
            'action_observed_or_graded': False,
            'warning': 'Queue only; no Monte Carlo run. Frame PTS and card claims are human declarations, not independently validated video evidence.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_plan_json')
    parser.add_argument('manual_cards_json')
    parser.add_argument('new_queue_json')
    args = parser.parse_args(argv)
    sources = [Path(args.reviewed_plan_json), Path(args.manual_cards_json)]
    dest = Path(args.new_queue_json)
    require(dest.suffix == '.json' and dest.parent.is_dir() and
            not dest.parent.is_symlink() and not dest.exists() and
            not dest.is_symlink() and dest.resolve() not in
            {p.resolve() for p in sources}, 'output must be a new JSON file')
    hashes = [digest(p) for p in sources]
    result = build(read(sources[0]), read(sources[1]), *hashes)
    require([digest(p) for p in sources] == hashes, 'input changed during processing')
    with dest.open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({'queue': str(dest), 'eligible': result['eligible_count'],
                      'blocked': result['blocked_count'], 'equity_executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
