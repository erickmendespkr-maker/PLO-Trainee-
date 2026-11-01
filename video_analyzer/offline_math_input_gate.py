"""Offline, fail-closed adapter from human-reviewed PLO street evidence to math inputs.

No OCR or video inference; no equity/EV computation; no poker client access.
Usage: python offline_math_input_gate.py reviewed.json assumptions.json output.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
STATUS = 'reviewed_math_candidate_manual_ranges_not_computed'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= 8_000_000, 'unsafe JSON file')
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, 'duplicate JSON key')
            obj[k] = v
        return obj
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant')
    with p.open(encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=unique, parse_constant=invalid_constant)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def cards(value, n, label):
    require(type(value) is list and len(value) == n and
            all(type(c) is str and len(c) == 2 and c[0] in RANKS and c[1] in SUITS for c in value) and
            len(set(value)) == len(value), 'invalid ' + label)
    return list(value)


def numeric(value, minimum, maximum, label):
    require(type(value) in (int, float) and math.isfinite(value) and
            minimum <= value <= maximum, 'invalid ' + label)
    return value


def build(review, assumptions, review_sha, assumptions_sha):
    require(type(review) is dict and review.get('schema_version') == 1 and
            review.get('status') == 'offline_human_reviewed_evidence_not_math_authorized' and
            review.get('automatic_ocr_math_authorization') is False and
            review.get('confidence_calibrated') is False and
            review.get('variant') in ('PLO5', 'PLO6') and
            type(review.get('hands')) is list, 'reviewed report not eligible')
    require(type(assumptions) is dict and set(assumptions) == {
        'schema_version', 'table_id', 'hand_id', 'source_review_sha256',
        'reviewer_attestation', 'range_source', 'villain_combos', 'pot_before_call',
        'to_call', 'seed', 'trials', 'model'}, 'invalid assumptions schema')
    require(assumptions['schema_version'] == 1 and
            assumptions['source_review_sha256'] == review_sha and
            assumptions['reviewer_attestation'] is True and
            type(assumptions['range_source']) is str and
            8 <= len(assumptions['range_source'].strip()) <= 300 and
            type(assumptions['table_id']) is str and
            type(assumptions['hand_id']) is str, 'missing explicit manual provenance')
    require(assumptions['model'] == 'heads_up_call_all_in_no_future_betting_no_rake',
            'unsupported EV model')
    pot = numeric(assumptions['pot_before_call'], 0, 1e12, 'pot')
    call = numeric(assumptions['to_call'], 0, 1e12, 'call')
    require(pot >= call > 0, 'call must be positive and included in existing pot')
    seed = assumptions['seed']
    trials = assumptions['trials']
    require(type(seed) is int and 0 <= seed < 2**63 and
            type(trials) is int and 100 <= trials <= 100000, 'invalid MC parameters')
    matched = [h for h in review['hands'] if type(h) is dict and
               h.get('table_id') == assumptions['table_id'] and
               h.get('hand_id') == assumptions['hand_id']]
    require(len(matched) == 1, 'hand not uniquely identified')
    hand = matched[0]
    require(hand.get('card_evidence_consistent') is True and
            hand.get('review_flags') == [] and
            hand.get('automatic_math_authorization') is False and
            type(hand.get('events')) is list, 'unresolved card evidence')
    count = 5 if review['variant'] == 'PLO5' else 6
    hero, board = None, []
    for event in hand['events']:
        require(type(event) is dict, 'invalid reviewed event')
        if event.get('kind') not in ('hero_cards', 'board'):
            continue
        require(event.get('decision') in ('confirm', 'correct') and
                event.get('reviewed_value') is not None, 'unreviewed/rejected card event')
        value = event['reviewed_value']
        if event['kind'] == 'hero_cards':
            new = cards(value, count, 'hero cards')
            require(hero is None or hero == new, 'conflicting hero cards')
            hero = new
        else:
            require(type(value) is list and len(value) in (3, 4, 5), 'invalid board length')
            new = cards(value, len(value), 'board')
            require(len(new) >= len(board) and new[:len(board)] == board, 'conflicting board progression')
            board = new
    require(hero is not None and not (set(hero) & set(board)), 'missing hero or duplicate cards')
    combos = assumptions['villain_combos']
    require(type(combos) is list and 1 <= len(combos) <= 2000, 'invalid range size')
    seen, valid = set(), []
    for entry in combos:
        require(type(entry) is dict and set(entry) == {'cards', 'weight'}, 'invalid range entry')
        hole = cards(entry['cards'], count, 'villain cards')
        require(not (set(hole) & (set(hero) | set(board))), 'range overlaps visible cards')
        key = tuple(sorted(hole))
        require(key not in seen, 'duplicate villain combo')
        seen.add(key)
        weight = numeric(entry['weight'], 0, 1e12, 'range weight')
        require(weight > 0, 'zero-weight range')
        valid.append({'cards': hole, 'weight': weight})
    return {'schema_version': 1, 'status': STATUS, 'variant': review['variant'],
            'table_id': assumptions['table_id'], 'hand_id': assumptions['hand_id'],
            'hero_cards': hero, 'board': board, 'villain_combos': valid,
            'pot_before_call': pot, 'to_call': call, 'seed': seed, 'trials': trials,
            'model': assumptions['model'], 'range_source': assumptions['range_source'],
            'source_review_sha256': review_sha, 'source_assumptions_sha256': assumptions_sha,
            'automatic_ocr_math_authorization': False,
            'confidence_note': 'Human reviewed fields and subjective villain range; not independently calibrated.',
            'warning': 'Candidate only. Equity/EV require separate computation and explicit model limitations.'}


def run(review_path, assumptions_path, output_path):
    review_path, assumptions_path, output_path = map(Path, (review_path, assumptions_path, output_path))
    require(len({p.resolve() for p in (review_path, assumptions_path, output_path)}) == 3,
            'paths must differ')
    require(output_path.parent.is_dir() and not output_path.parent.is_symlink() and
            not output_path.exists() and not output_path.is_symlink(), 'unsafe output')
    rsha, asha = digest(review_path), digest(assumptions_path)
    report = build(load(review_path), load(assumptions_path), rsha, asha)
    require(digest(review_path) == rsha and digest(assumptions_path) == asha, 'source changed')
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=output_path.parent,
                                         prefix='.plo_math_gate_', suffix='.tmp', delete=False) as f:
            temp_name = f.name
            json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        require(not output_path.exists() and not output_path.is_symlink(), 'output collision')
        os.link(temp_name, output_path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_json')
    parser.add_argument('manual_assumptions_json')
    parser.add_argument('output_json')
    args = parser.parse_args()
    result = run(args.reviewed_json, args.manual_assumptions_json, args.output_json)
    print(result['status'])
