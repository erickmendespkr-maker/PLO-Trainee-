"""Fail-closed, timestamp-scoped math candidate for *recorded* PLO5/PLO6 hands.

Unlike the legacy whole-hand gate, this adapter NEVER supplies board cards that
appeared after the selected decision. It delegates card/range/pot validation to
``offline_math_input_gate``. No equity/EV is calculated or authorized here.

Usage: python offline_math_decision_snapshot.py REVIEW.json ASSUMPTIONS.json NEW_OUTPUT.json
ASSUMPTIONS uses offline_math_input_gate schema plus:
  decision_timestamp_seconds: number
  decision_street: preflop|flop|turn|river
Only explicit, human-reviewed observations at/before the decision are eligible.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import tempfile

import offline_math_input_gate as gate

STREETS = ('preflop', 'flop', 'turn', 'river')
EXPECTED_BOARD = {'preflop': 0, 'flop': 3, 'turn': 4, 'river': 5}
EXTRA = {'decision_timestamp_seconds', 'decision_street'}
STATUS = 'timestamp_scoped_reviewed_math_candidate_not_computed'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical_cards(value, expected, label):
    require(type(value) is list and len(value) == expected, 'invalid ' + label)
    normalized = []
    for c in value:
        require(type(c) is str and len(c) == 2 and c[0] in gate.RANKS and
                c[1] in 'cdhsCDHS', 'invalid ' + label)
        normalized.append(c[0] + c[1].lower())
    require(len(set(normalized)) == len(normalized), 'duplicate ' + label)
    return normalized


def build(review, assumptions, review_sha, assumptions_sha):
    require(type(review) is dict and type(assumptions) is dict,
            'invalid input envelope')
    expected_keys = {'schema_version', 'table_id', 'hand_id', 'source_review_sha256',
                     'reviewer_attestation', 'range_source', 'villain_combos',
                     'pot_before_call', 'to_call', 'seed', 'trials', 'model'} | EXTRA
    require(set(assumptions) == expected_keys, 'invalid timestamped assumptions schema')
    t = assumptions['decision_timestamp_seconds']
    street = assumptions['decision_street']
    require(type(t) in (int, float) and math.isfinite(t) and t >= 0 and
            street in STREETS, 'invalid decision timestamp or street')
    require(review.get('status') == 'offline_human_reviewed_evidence_not_math_authorized' and
            review.get('automatic_ocr_math_authorization') is False and
            review.get('confidence_calibrated') is False and
            review.get('variant') in ('PLO5', 'PLO6') and
            type(review.get('hands')) is list, 'review not eligible')
    matches = [h for h in review['hands'] if type(h) is dict and
               h.get('table_id') == assumptions['table_id'] and
               h.get('hand_id') == assumptions['hand_id']]
    require(len(matches) == 1, 'ambiguous hand')
    hand = matches[0]
    start, end = hand.get('start_seconds'), hand.get('end_seconds')
    require(type(start) in (int, float) and type(end) in (int, float) and
            math.isfinite(start) and math.isfinite(end) and
            0 <= start <= t <= end and end > start, 'decision outside hand interval')
    require(hand.get('review_flags') == [] and
            hand.get('card_evidence_consistent') is True and
            hand.get('automatic_math_authorization') is False and
            type(hand.get('events')) is list, 'unresolved hand evidence')
    n = 5 if review['variant'] == 'PLO5' else 6
    filtered = []
    prev_time, prev_street = start, -1
    last_hero, last_board = None, []
    for event in hand['events']:
        require(type(event) is dict and event.get('street') in STREETS and
                type(event.get('timestamp_seconds')) in (int, float) and
                math.isfinite(event['timestamp_seconds']), 'event missing timestamp/street')
        et, es = event['timestamp_seconds'], STREETS.index(event['street'])
        require(start <= et <= end and et >= prev_time and es >= prev_street,
                'invalid chronological event sequence')
        prev_time, prev_street = et, es
        kind = event.get('kind')
        if kind not in ('hero_cards', 'board'):
            continue
        # Even future card proposals must have valid street/shape, but are never
        # used to calculate an earlier decision's equity.
        require(kind != 'board' or event['street'] != 'preflop',
                'board cannot appear preflop')
        if et > t:
            continue
        require(es <= STREETS.index(street), 'future street at decision timestamp')
        require(event.get('decision') in ('confirm', 'correct') and
                event.get('reviewed_value') is not None,
                'unreviewed card evidence at decision')
        normalized = copy.deepcopy(event)
        if kind == 'hero_cards':
            cards = canonical_cards(event['reviewed_value'], n, 'hero cards')
            require(last_hero is None or last_hero == cards,
                    'conflicting hero cards')
            last_hero = cards
        else:
            cards = canonical_cards(event['reviewed_value'],
                                    EXPECTED_BOARD[event['street']], 'board cards')
            require(len(cards) >= len(last_board) and
                    cards[:len(last_board)] == last_board,
                    'conflicting board progression')
            last_board = cards
        normalized['reviewed_value'] = cards
        filtered.append(normalized)
    require(last_hero is not None, 'hero cards not known at decision')
    require(len(last_board) == EXPECTED_BOARD[street],
            'board not fully observed at selected decision street')
    require(not (set(last_hero) & set(last_board)), 'hero/board overlap')
    scoped = copy.deepcopy(review)
    scoped['hands'] = [copy.deepcopy(hand)]
    scoped['hands'][0]['events'] = filtered
    params = {k: copy.deepcopy(v) for k, v in assumptions.items() if k not in EXTRA}
    require(type(params['villain_combos']) is list, 'invalid opponent range')
    for entry in params['villain_combos']:
        require(type(entry) is dict and 'cards' in entry, 'invalid opponent combo')
        entry['cards'] = canonical_cards(entry['cards'], n, 'opponent cards')
    candidate = gate.build(scoped, params, review_sha, assumptions_sha)
    candidate['status'] = STATUS
    candidate['decision_timestamp_seconds'] = t
    candidate['decision_street'] = street
    candidate['decision_board_cards'] = len(last_board)
    candidate['source_full_review_sha256'] = review_sha
    candidate['source_full_assumptions_sha256'] = assumptions_sha
    candidate['warning'] = ('Timestamp-scoped human assertions and hypothetical opponent '
                            'ranges only; no equity/EV or verified strategy verdict.')
    return candidate


def run(review_path, assumptions_path, output_path):
    review_path, assumptions_path, output_path = map(Path,
        (review_path, assumptions_path, output_path))
    require(len({p.resolve() for p in (review_path, assumptions_path, output_path)}) == 3,
            'input/output paths must differ')
    require(output_path.parent.is_dir() and not output_path.parent.is_symlink() and
            not output_path.exists() and not output_path.is_symlink(),
            'unsafe output')
    review_sha, assumptions_sha = gate.digest(review_path), gate.digest(assumptions_path)
    result = build(gate.load(review_path), gate.load(assumptions_path),
                   review_sha, assumptions_sha)
    require(gate.digest(review_path) == review_sha and
            gate.digest(assumptions_path) == assumptions_sha, 'source changed')
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=output_path.parent,
                                         prefix='.plo_decision_', suffix='.tmp',
                                         delete=False) as f:
            temp_name = f.name
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        require(not output_path.exists() and not output_path.is_symlink(),
                'output collision')
        os.link(temp_name, output_path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reviewed_json')
    p.add_argument('timestamped_assumptions_json')
    p.add_argument('new_output_json')
    a = p.parse_args()
    print(run(a.reviewed_json, a.timestamped_assumptions_json,
              a.new_output_json)['status'])
