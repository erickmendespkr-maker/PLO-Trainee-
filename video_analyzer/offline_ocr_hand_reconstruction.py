"""Reconstruct *unverified* per-hand OCR candidates from a review ledger.

Usage: python offline_ocr_hand_reconstruction.py LEDGER.json NEW_RECONSTRUCTION.json

This is a read-only, offline diagnostic. It does not authenticate human choices,
read video, infer hidden cards, emit math-ready annotations, or run equity/EV.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

import offline_reviewed_hand_math_queue as queue

SHA = re.compile(r'[0-9a-f]{64}\Z')
FIELDS = {'hero_card', 'board_card', 'action', 'pot', 'stack', 'variant'}
CHOICES = {'accepted', 'rejected', 'unknown'}
MAX_ROWS = 6000
MAX_HANDS = 100


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def valid_sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def valid_text(value):
    return value is None or (type(value) is str and 1 <= len(value) <= 80 and
                             all(32 <= ord(c) < 127 for c in value))


def valid_number(value, minimum, maximum):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def validate(ledger):
    require(type(ledger) is dict and ledger.get('schema_version') == 1 and
            ledger.get('status') == 'offline_human_selection_ledger_not_math_ready' and
            ledger.get('eligible_for_equity') == 0 and
            type(ledger.get('eligible_for_equity')) is int and
            ledger.get('equity_or_ev_calculated') is False and
            ledger.get('human_selection_not_authenticated') is True and
            ledger.get('original_video_cards_not_independently_verified') is True and
            ledger.get('manual_review_required') is True and
            type(ledger.get('decisions')) is list and
            type(ledger.get('hands')) is list and
            1 <= len(ledger['hands']) <= MAX_HANDS and
            len(ledger['decisions']) <= MAX_ROWS and
            all(valid_sha(ledger.get(key)) for key in (
                'source_video_sha256_claim', 'source_plan_sha256',
                'source_worksheet_sha256', 'source_frame_manifest_sha256',
                'source_draft_sha256')), 'invalid or unsafe OCR review ledger')
    hands = {}
    for hand in ledger['hands']:
        require(type(hand) is dict and set(hand) == {
            'hand_id', 'table_id', 'review_flags',
            'selected_card_slots_unverified', 'math_ready'} and
            type(hand['hand_id']) is str and queue.ID.fullmatch(hand['hand_id']) and
            hand['hand_id'] not in hands and
            type(hand['table_id']) is str and queue.ID.fullmatch(hand['table_id']) and
            hand['math_ready'] is False and
            type(hand['selected_card_slots_unverified']) is int and
            0 <= hand['selected_card_slots_unverified'] <= 11 and
            type(hand['review_flags']) is list and
            all(type(x) is str and len(x) <= 80 for x in hand['review_flags']),
            'invalid or duplicated hand record')
        hands[hand['hand_id']] = hand
    require(len({h['table_id'] for h in hands.values()}) <= 4,
            'more than four tables')
    seen_indices = set()
    rows = {key: [] for key in hands}
    for raw in ledger['decisions']:
        require(type(raw) is dict and set(raw) == {
            'observation_index', 'hand_id', 'table_id', 'field', 'slot',
            'pts_seconds', 'ocr_suggestion', 'ocr_confidence_raw_uncalibrated',
            'human_selection_unverified', 'corrected_text_unverified',
            'frame_sha256', 'frame_pts_seconds'}, 'invalid observation fields')
        hand_id, field, slot = raw['hand_id'], raw['field'], raw['slot']
        require(type(hand_id) is str and hand_id in hands and
                raw['table_id'] == hands[hand_id]['table_id'] and
                type(raw['observation_index']) is int and
                0 <= raw['observation_index'] < len(ledger['decisions']) and
                raw['observation_index'] not in seen_indices and
                type(field) is str and field in FIELDS and
                ((type(slot) is int and 0 <= slot < (6 if field == 'hero_card' else 5))
                 if field in ('hero_card', 'board_card') else slot is None) and
                valid_number(raw['pts_seconds'], 0, 14400) and
                valid_number(raw['ocr_confidence_raw_uncalibrated'], 0, 1) and
                type(raw['ocr_suggestion']) is str and valid_text(raw['ocr_suggestion']) and
                type(raw['human_selection_unverified']) is str and
                raw['human_selection_unverified'] in CHOICES and
                valid_text(raw['corrected_text_unverified']) and
                (raw['frame_sha256'] is None or valid_sha(raw['frame_sha256'])) and
                (raw['frame_pts_seconds'] is None or
                 valid_number(raw['frame_pts_seconds'], 0, 14400)) and
                ((raw['frame_sha256'] is None) == (raw['frame_pts_seconds'] is None)) and
                (raw['human_selection_unverified'] != 'accepted' or
                 (raw['corrected_text_unverified'] is None and
                  raw['frame_sha256'] is not None and
                  abs(raw['pts_seconds'] - raw['frame_pts_seconds']) <= .25)),
                'invalid or unbound observation')
        seen_indices.add(raw['observation_index'])
        rows[hand_id].append(raw)
    require(seen_indices == set(range(len(ledger['decisions']))),
            'observation indices must be complete')
    for hand_id, hand in hands.items():
        selected = {(r['field'], r['slot']) for r in rows[hand_id]
                    if r['field'] in ('hero_card', 'board_card') and
                    r['human_selection_unverified'] == 'accepted' and
                    len(r['ocr_suggestion']) == 2 and
                    r['ocr_suggestion'][0] in queue.RANKS and
                    r['ocr_suggestion'][1] in queue.SUITS}
        require(len(selected) == hand['selected_card_slots_unverified'],
                'hand summary and selected card slots disagree')
    return hands, rows


def build(ledger, ledger_sha):
    require(valid_sha(ledger_sha), 'invalid source ledger SHA-256')
    hands, rows_by_hand = validate(ledger)
    result = []
    for hand_id, source in hands.items():
        rows = rows_by_hand[hand_id]
        flags = set(source['review_flags'])
        slots = {'hero_card': {}, 'board_card': {}}
        card_evidence = []
        corrections = []
        other = {'variant': [], 'action': [], 'pot': [], 'stack': []}
        for row in rows:
            field = row['field']
            if row['corrected_text_unverified'] is not None:
                corrections.append({'field': field, 'slot': row['slot'],
                                    'candidate_text': row['corrected_text_unverified'],
                                    'pts_seconds': row['pts_seconds']})
            if row['human_selection_unverified'] != 'accepted':
                continue
            value = row['ocr_suggestion']
            if field in slots:
                if len(value) != 2 or value[0] not in queue.RANKS or value[1] not in queue.SUITS:
                    flags.add('invalid_selected_card_text')
                else:
                    slots[field].setdefault(row['slot'], set()).add(value)
                    card_evidence.append({'field': field, 'slot': row['slot'],
                                          'candidate': value,
                                          'pts_seconds': row['pts_seconds'],
                                          'frame_pts_seconds': row['frame_pts_seconds'],
                                          'frame_sha256': row['frame_sha256'],
                                          'ocr_confidence_raw_uncalibrated':
                                              row['ocr_confidence_raw_uncalibrated']})
            else:
                other[field].append({'value': value, 'pts_seconds': row['pts_seconds']})
        for field in slots:
            if any(len(values) > 1 for values in slots[field].values()):
                flags.add('conflicting_selected_slot')
        all_cards = [next(iter(values)) for field in slots for values in slots[field].values()
                     if len(values) == 1]
        if len(all_cards) != len(set(all_cards)):
            flags.add('selected_card_repeated_across_slots')
        variants = {r['value'] for r in other['variant']}
        if len(variants) > 1:
            flags.add('conflicting_variant_candidates')
        variant = next(iter(variants)) if len(variants) == 1 else None
        if variant not in ('PLO5', 'PLO6'):
            flags.add('variant_not_unambiguously_selected')
            variant = None
        expected_hero = 5 if variant == 'PLO5' else 6 if variant == 'PLO6' else None
        hero_slots = slots['hero_card']
        board_slots = slots['board_card']
        if expected_hero is None:
            flags.add('hero_card_count_unknown')
        elif any(i >= expected_hero for i in hero_slots):
            flags.add('hero_slot_incompatible_with_variant')
        elif any(i not in hero_slots or len(hero_slots[i]) != 1 for i in range(expected_hero)):
            flags.add('incomplete_hero_cards')
        if any(i not in board_slots or len(board_slots[i]) != 1 for i in range(3)):
            flags.add('incomplete_flop_board')
        if any(i in board_slots and i - 1 not in board_slots for i in (3, 4)):
            flags.add('board_street_gap')
        if not other['action']:
            flags.add('actions_not_selected')
        if not other['pot']:
            flags.add('pot_not_selected')
        if not rows:
            flags.add('no_review_observations')
        serialized = {field: {str(slot): sorted(values) for slot, values in sorted(slots[field].items())}
                      for field in slots}
        result.append({'hand_id': hand_id, 'table_id': source['table_id'],
                       'variant_candidate_unverified': variant,
                       'expected_hero_cards_if_variant_correct': expected_hero,
                       'card_candidates_unverified': serialized,
                       'card_evidence_unverified': card_evidence,
                       'other_selected_candidates_unverified': other,
                       'corrections_not_accepted_as_evidence': corrections,
                       'review_flags': sorted(flags),
                       'selected_observations': sum(r['human_selection_unverified'] == 'accepted' for r in rows),
                       'math_ready': False, 'eligible_for_equity': False})
    return {'schema_version': 1,
            'status': 'offline_ocr_hand_reconstruction_unverified_not_math_ready',
            'source_ledger_sha256': ledger_sha,
            'source_video_sha256_claim': ledger['source_video_sha256_claim'],
            'hands': result,
            'hand_count': len(result),
            'eligible_for_equity': 0,
            'equity_or_ev_calculated': False,
            'original_video_cards_not_independently_verified': True,
            'human_review_required': True,
            'warning': 'Unverified candidate reconstruction only. No inferred hidden cards, confirmed hand histories, equity inputs, or EV.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger_json')
    parser.add_argument('new_reconstruction_json')
    args = parser.parse_args(argv)
    source, target = Path(args.ledger_json), Path(args.new_reconstruction_json)
    require(target.suffix == '.json' and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink() and target.resolve() != source.resolve(),
            'output must be a new distinct JSON file')
    before = queue.digest(source)
    report = build(queue.read(source), before)
    require(queue.digest(source) == before, 'source changed during reconstruction')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(target), 'hands': report['hand_count'],
                      'eligible_for_equity': 0, 'equity_executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
