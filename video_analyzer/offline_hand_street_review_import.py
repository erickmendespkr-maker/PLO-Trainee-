"""Import a PLO5/PLO6 offline hand/street review draft without granting math eligibility.

Usage:
    python offline_hand_street_review_import.py RECONSTRUCTION.json WORKSHEET.json DRAFT.json NEW_LEDGER.json

A browser's 'confirmed_by_reviewer' value is an unauthenticated assertion, NOT
independent video evidence. The output cannot be submitted directly to equity/EV.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import offline_hand_street_review as review

CARD = re.compile(r'[23456789TJQKA][cdhs]\Z')
AMOUNT = re.compile(r'(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?\Z')
STATUSES = {'unreviewed', 'confirmed_by_reviewer', 'rejected', 'unknown'}
MAX_FIELDS = 1600


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def valid_value(field, value):
    if type(value) is not str or not 1 <= len(value) <= 80:
        return False
    if field in ('hero_card', 'board_card'):
        return CARD.fullmatch(value) is not None
    if field == 'variant':
        return value in ('PLO5', 'PLO6')
    if field in ('pot', 'stack'):
        return AMOUNT.fullmatch(value) is not None
    return all(32 <= ord(ch) < 127 for ch in value)


def build(reconstruction_path, worksheet_path, draft_path):
    paths = [Path(p) for p in (reconstruction_path, worksheet_path, draft_path)]
    # The original reconstruction must reproduce the worksheet exactly; a forged
    # worksheet cannot change OCR candidates, field positions or provenance.
    hashes = [review.digest(p) for p in paths]
    reconstruction, worksheet, draft = [review.read(p) for p in paths]
    expected = review.worksheet(reconstruction, hashes[0])
    require(type(worksheet) is dict and worksheet == expected,
            'worksheet does not match original reconstruction')
    require(type(draft) is dict and set(draft) == set(expected),
            'draft root fields mismatch')
    for key in expected:
        if key != 'hands':
            require(type(draft[key]) is type(expected[key]) and draft[key] == expected[key],
                    'draft provenance or metadata changed')
    require(type(draft['hands']) is list and len(draft['hands']) == len(expected['hands']),
            'draft hand count changed')
    ledger_hands = []
    total_fields = 0
    total_confirmed = 0
    for original, edited in zip(expected['hands'], draft['hands']):
        require(type(edited) is dict and set(edited) == set(original), 'draft hand keys changed')
        for key in original:
            if key != 'fields':
                require(type(edited[key]) is type(original[key]) and edited[key] == original[key],
                        'draft hand identity or metadata changed')
        require(type(edited['fields']) is list and len(edited['fields']) == len(original['fields']),
                'draft field count changed')
        entries = []
        for base, raw in zip(original['fields'], edited['fields']):
            total_fields += 1
            require(total_fields <= MAX_FIELDS, 'too many review fields')
            require(type(raw) is dict and set(raw) == set(base), 'draft field keys changed')
            for key in base:
                if key not in ('review_status', 'reviewer_value'):
                    require(type(raw[key]) is type(base[key]) and raw[key] == base[key],
                            'draft changed immutable OCR field')
            status, value = raw['review_status'], raw['reviewer_value']
            require(type(status) is str and status in STATUSES, 'invalid review status')
            if status == 'confirmed_by_reviewer':
                require(valid_value(base['field'], value), 'invalid reviewer declaration')
                total_confirmed += 1
            else:
                require(value is None, 'non-confirmed field has reviewer value')
            entries.append({'field': base['field'], 'slot': base['slot'],
                            'street': base['street'], 'ocr_candidates_unverified': base['ocr_candidates_unverified'],
                            'review_status': status, 'reviewer_value_unverified': value,
                            'value_present_in_ocr_candidates': (value in base['ocr_candidates_unverified']
                                                                if value is not None else None)})
        confirmed = {(e['field'], e['slot']): e['reviewer_value_unverified']
                     for e in entries if e['review_status'] == 'confirmed_by_reviewer'}
        flags = set(original['review_flags'])
        variant = confirmed.get(('variant', None))
        if variant is None:
            flags.add('variant_not_confirmed')
        expected_count = 5 if variant == 'PLO5' else 6 if variant == 'PLO6' else None
        hero = {slot: card for (field, slot), card in confirmed.items() if field == 'hero_card'}
        board = {slot: card for (field, slot), card in confirmed.items() if field == 'board_card'}
        if expected_count is not None:
            if any(slot >= expected_count for slot in hero):
                flags.add('hero_slot_incompatible_with_variant')
            if len(hero) != expected_count or any(i not in hero for i in range(expected_count)):
                flags.add('hero_cards_incomplete')
        if any(slot in board and slot - 1 not in board for slot in (3, 4)):
            flags.add('board_street_gap')
        if 0 < len(board) < 3:
            flags.add('partial_flop_claim')
        if len(set([*hero.values(), *board.values()])) != len(hero) + len(board):
            flags.add('duplicate_card_claim')
        for field in ('action', 'pot', 'stack'):
            if (field, None) not in confirmed:
                flags.add(field + '_not_confirmed')
        if ('action', None) in confirmed:
            flags.add('action_street_not_verified')
        if any(e['value_present_in_ocr_candidates'] is False for e in entries):
            flags.add('reviewer_value_differs_from_ocr')
        ledger_hands.append({'hand_id': original['hand_id'], 'table_id': original['table_id'],
                             'review_flags': sorted(flags), 'fields': entries,
                             'confirmed_declarations_unverified': sum(e['review_status'] == 'confirmed_by_reviewer'
                                                                      for e in entries),
                             'math_ready': False, 'eligible_for_equity': False})
    require(hashes == [review.digest(p) for p in paths], 'input changed during import')
    return {'schema_version': 1,
            'status': 'offline_hand_street_review_import_unverified_not_math_ready',
            'source_reconstruction_sha256': hashes[0], 'source_worksheet_sha256': hashes[1],
            'source_draft_sha256': hashes[2],
            'source_ledger_sha256': expected['source_ledger_sha256'],
            'source_video_sha256_claim': expected['source_video_sha256_claim'],
            'hand_count': len(ledger_hands), 'field_count': total_fields,
            'reviewer_declarations_unverified': total_confirmed, 'hands': ledger_hands,
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'reviewer_claims_not_authenticated': True,
            'original_video_cards_not_independently_verified': True,
            'human_video_evidence_review_required': True,
            'warning': 'Reviewer declarations are not independently authenticated against video. No equity, EV or math-ready hand is produced.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reconstruction_json')
    parser.add_argument('worksheet_json')
    parser.add_argument('draft_json')
    parser.add_argument('new_ledger_json')
    args = parser.parse_args(argv)
    sources = [Path(p) for p in (args.reconstruction_json, args.worksheet_json, args.draft_json)]
    target = Path(args.new_ledger_json)
    require(target.suffix == '.json' and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink() and target.resolve() not in {p.resolve() for p in sources},
            'output must be a new distinct JSON file')
    result = build(*sources)
    with target.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    print(json.dumps({'hands': result['hand_count'], 'fields': result['field_count'],
                      'reviewer_declarations_unverified': result['reviewer_declarations_unverified'],
                      'eligible_for_equity': 0, 'output': str(target)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
