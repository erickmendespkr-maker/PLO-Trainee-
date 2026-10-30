"""Validate an offline OCR review draft against its original worksheet and frames.

Usage: python offline_ocr_review_draft_import.py FRAMES_DIR WORKSHEET.json DRAFT.json NEW_LEDGER.json

A browser draft is an unauthenticated human selection, NOT independent proof that
cards are visible. This importer never creates math-ready annotations or equity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import offline_ocr_frame_review_page as page

DECISIONS = {'unknown', 'rejected', 'accepted'}
FIELDS = {'hero_card', 'board_card', 'action', 'pot', 'stack', 'variant'}
MAX_DRAFT_BYTES = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def valid_text(value):
    return value is None or (type(value) is str and
                             1 <= len(value) <= 80 and
                             all(32 <= ord(ch) < 127 for ch in value))


def build(frame_dir, worksheet_path, draft_path):
    frame_dir, worksheet_path, draft_path = map(Path, (frame_dir, worksheet_path, draft_path))
    require(draft_path.is_file() and not draft_path.is_symlink() and
            0 < draft_path.stat().st_size <= MAX_DRAFT_BYTES, 'invalid review draft')
    packet = page.build(frame_dir, worksheet_path)
    draft = page.read_json(draft_path)
    require(type(draft) is dict and set(draft) == {
        'schema_version', 'status', 'source_plan_sha256',
        'source_worksheet_sha256', 'source_frame_manifest_sha256',
        'decisions', 'eligible_for_equity', 'equity_or_ev_calculated'} and
        type(draft['schema_version']) is int and draft['schema_version'] == 1 and
        draft['status'] == 'human_review_draft_not_confirmed_for_math' and
        draft['source_plan_sha256'] == packet['source_plan_sha256'] and
        draft['source_worksheet_sha256'] == packet['source_worksheet_sha256'] and
        draft['source_frame_manifest_sha256'] == packet['source_frame_manifest_sha256'] and
        type(draft['eligible_for_equity']) is int and draft['eligible_for_equity'] == 0 and
        draft['equity_or_ev_calculated'] is False and
        type(draft['decisions']) is list,
        'draft schema or provenance mismatch')
    expected = [(hand, obs) for hand in packet['hands'] for obs in hand['observations']]
    require(len(draft['decisions']) == len(expected), 'draft decision count mismatch')
    rows = []
    for i, (raw, (hand, obs)) in enumerate(zip(draft['decisions'], expected)):
        require(type(raw) is dict and set(raw) == {
            'hand_id', 'table_id', 'field', 'slot', 'pts_seconds',
            'decision', 'corrected_value', 'frame_sha256'},
            'invalid decision fields')
        require(raw['hand_id'] == hand['hand_id'] and
                raw['table_id'] == hand['table_id'] and
                raw['field'] == obs['field'] and raw['field'] in FIELDS and
                type(raw['slot']) is type(obs['slot']) and raw['slot'] == obs['slot'] and
                page.valid_pts(raw['pts_seconds']) and
                raw['pts_seconds'] == obs['pts_seconds'] and
                type(raw['decision']) is str and raw['decision'] in DECISIONS and
                valid_text(raw['corrected_value']),
                'draft observation mismatch')
        frame = (packet['frames'][obs['frame_index']]
                 if obs['frame_index'] is not None else None)
        require(raw['frame_sha256'] == (frame['sha256'] if frame else None),
                'draft frame hash mismatch')
        if raw['decision'] == 'accepted':
            require(obs['can_accept_after_human_review'] and frame is not None,
                    'accepted observation lacks exact-time frame')
            require(raw['corrected_value'] is None,
                    'corrected text cannot be accepted as original OCR')
        rows.append({'observation_index': i, 'hand_id': hand['hand_id'],
                     'table_id': hand['table_id'], 'field': obs['field'],
                     'slot': obs['slot'], 'pts_seconds': obs['pts_seconds'],
                     'ocr_suggestion': obs['suggested'],
                     'ocr_confidence_raw_uncalibrated': obs['confidence_raw'],
                     'human_selection_unverified': raw['decision'],
                     'corrected_text_unverified': raw['corrected_value'],
                     'frame_sha256': raw['frame_sha256'],
                     'frame_pts_seconds': frame['pts_seconds'] if frame else None})
    hands = []
    for hand in packet['hands']:
        subset = [r for r in rows if r['hand_id'] == hand['hand_id']]
        flags = set()
        slot_values = {}
        for row in subset:
            if row['human_selection_unverified'] != 'accepted' or row['field'] not in ('hero_card', 'board_card'):
                continue
            card = row['ocr_suggestion']
            if not (len(card) == 2 and card[0] in '23456789TJQKA' and card[1] in 'cdhs'):
                flags.add('invalid_selected_card_text')
                continue
            slot_values.setdefault((row['field'], row['slot']), set()).add(card)
        if any(len(values) > 1 for values in slot_values.values()):
            flags.add('conflicting_selected_slot')
        flattened = [next(iter(v)) for v in slot_values.values() if len(v) == 1]
        if len(flattened) != len(set(flattened)):
            flags.add('selected_card_repeated_across_slots')
        if not slot_values:
            flags.add('no_selected_card_evidence')
        hands.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                      'review_flags': sorted(flags),
                      'selected_card_slots_unverified': len(slot_values),
                      'math_ready': False})
    return {'schema_version': 1,
            'status': 'offline_human_selection_ledger_not_math_ready',
            'source_video_sha256_claim': packet['source_video_sha256'],
            'source_plan_sha256': packet['source_plan_sha256'],
            'source_worksheet_sha256': packet['source_worksheet_sha256'],
            'source_frame_manifest_sha256': packet['source_frame_manifest_sha256'],
            'source_draft_sha256': page.sha256(draft_path),
            'decisions': rows, 'hands': hands,
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'human_selection_not_authenticated': True,
            'original_video_cards_not_independently_verified': True,
            'manual_review_required': True,
            'warning': 'Selections are unauthenticated browser assertions. This ledger is not a card confirmation, a Monte Carlo queue, or an EV estimate.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame_directory')
    parser.add_argument('worksheet_json')
    parser.add_argument('draft_json')
    parser.add_argument('new_ledger_json')
    args = parser.parse_args(argv)
    sources = [Path(args.frame_directory)/'manifest.json',
               Path(args.worksheet_json), Path(args.draft_json)]
    dest = Path(args.new_ledger_json)
    require(dest.suffix == '.json' and dest.parent.is_dir() and
            not dest.parent.is_symlink() and not dest.exists() and
            not dest.is_symlink() and dest.resolve() not in
            {path.resolve() for path in sources}, 'output must be a new distinct JSON file')
    before = [page.sha256(p) for p in sources]
    result = build(args.frame_directory, args.worksheet_json, args.draft_json)
    require(before == [page.sha256(p) for p in sources], 'source changed during import')
    with dest.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    print(json.dumps({'ledger': str(dest), 'decisions': len(result['decisions']),
                      'hands': len(result['hands']), 'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
