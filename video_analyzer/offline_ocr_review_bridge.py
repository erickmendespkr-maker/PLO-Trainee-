"""Offline OCR/vision proposal -> human review worksheet and blocked math draft.

Usage: python offline_ocr_review_bridge.py PLAN.json PROPOSALS.json NEW_WORKSHEET.json NEW_ANNOTATIONS.json

Input is a normalized, *unverified* OCR/vision proposal stream; no OCR is run
here. The worksheet retains all candidates with timestamps and normalized ROIs.
The companion annotations file deliberately contains NO confirmed cards or
human_frame_review evidence. It must never enable Monte Carlo without an
independent, explicit human review. No real-time poker access.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import offline_reviewed_hand_math_queue as queue

MAX_OBSERVATIONS = 6000
MAX_TEXT = 80
FIELDS = {'hero_card', 'board_card', 'pot', 'stack', 'action', 'variant'}
ENGINES = {'tesseract', 'vision', 'synthetic'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(x, lo, hi):
    return type(x) in (int, float) and math.isfinite(x) and lo <= x <= hi


def validate_observation(item, clips):
    require(type(item) is dict and set(item) ==
            {'hand_id', 'table_id', 'field', 'slot', 'value', 'pts_seconds',
             'confidence', 'roi', 'engine'}, 'invalid proposal fields')
    hand_id = item['hand_id']
    require(type(hand_id) is str and hand_id in clips, 'unknown proposal hand')
    clip = clips[hand_id]
    require(item['table_id'] == clip['table_id'], 'cross-table proposal')
    field, slot = item['field'], item['slot']
    require(type(field) is str and field in FIELDS, 'invalid proposal field')
    if field in ('hero_card', 'board_card'):
        require(type(slot) is int and 0 <= slot < (6 if field == 'hero_card' else 5),
                'invalid card slot')
    else:
        require(slot is None, 'non-card proposal has slot')
    require(type(item['value']) is str and 1 <= len(item['value']) <= MAX_TEXT and
            all(32 <= ord(c) < 127 for c in item['value']), 'invalid OCR text')
    require(number(item['pts_seconds'], clip['start_seconds'], clip['end_seconds']),
            'proposal timestamp outside reviewed hand')
    require(number(item['confidence'], 0, 1), 'invalid raw confidence')
    require(type(item['engine']) is str and item['engine'] in ENGINES,
            'invalid OCR engine')
    roi = item['roi']
    require(type(roi) is dict and set(roi) == {'x', 'y', 'w', 'h'} and
            all(number(roi[k], 0, 1) for k in roi) and
            roi['w'] > 0 and roi['h'] > 0 and
            roi['x'] + roi['w'] <= 1 + 1e-9 and
            roi['y'] + roi['h'] <= 1 + 1e-9, 'invalid normalized ROI')
    return item


def build(plan, proposals, plan_sha, proposals_sha):
    clips = queue.validate_plan(plan)
    require(type(proposals) is dict and set(proposals) ==
            {'schema_version', 'status', 'source_plan_sha256',
             'source_video_sha256_claim', 'observations'} and
            proposals['schema_version'] == 1 and
            proposals['status'] == 'offline_ocr_proposals_unverified' and
            proposals['source_plan_sha256'] == plan_sha and
            proposals['source_video_sha256_claim'] == plan['source_video_sha256'] and
            type(proposals['observations']) is list and
            len(proposals['observations']) <= MAX_OBSERVATIONS,
            'unbound or invalid OCR proposal batch')
    by_hand = {hand_id: [] for hand_id in clips}
    for raw in proposals['observations']:
        item = validate_observation(raw, clips)
        by_hand[item['hand_id']].append(item)
    rows = []
    for hand_id, clip in clips.items():
        obs = sorted(by_hand[hand_id], key=lambda o: (o['pts_seconds'], o['field'],
                    -1 if o['slot'] is None else o['slot'], o['value'], o['engine']))
        slots = {}
        flags = set()
        for item in obs:
            if item['confidence'] < .8:
                flags.add('low_raw_ocr_confidence')
            if item['field'] in ('hero_card', 'board_card'):
                key = item['field'] + ':' + str(item['slot'])
                slots.setdefault(key, set()).add(item['value'])
                if not (len(item['value']) == 2 and
                        item['value'][0] in queue.RANKS and
                        item['value'][1] in queue.SUITS):
                    flags.add('unrecognized_card_text')
        if any(len(values) > 1 for values in slots.values()):
            flags.add('conflicting_slot_candidates')
        unique_cards = [next(iter(values)) for values in slots.values()
                        if len(values) == 1 and len(next(iter(values))) == 2 and
                        next(iter(values))[0] in queue.RANKS and
                        next(iter(values))[1] in queue.SUITS]
        if len(set(unique_cards)) != len(unique_cards):
            flags.add('same_card_proposed_in_multiple_slots')
        if not obs:
            flags.add('no_ocr_observations')
        rows.append({'hand_id': hand_id, 'table_id': clip['table_id'],
                     'start_seconds': clip['start_seconds'],
                     'end_seconds': clip['end_seconds'],
                     'observations': obs, 'review_flags': sorted(flags),
                     'human_review_required': True,
                     'machine_cards_confirmed': False,
                     'eligible_for_equity': False})
    worksheet = {
        'schema_version': 1,
        'status': 'ocr_review_worksheet_not_confirmed',
        'source_plan_sha256': plan_sha,
        'source_proposals_sha256': proposals_sha,
        'source_video_sha256_claim': plan['source_video_sha256'],
        'ocr_confidence_is_uncalibrated': True,
        'card_claims_verified': False,
        'actions_verified': False,
        'equity_or_ev_calculated': False,
        'hands': rows,
        'warning': 'All values are unverified OCR/vision suggestions. Inspect original frames and create independent human-confirmed annotations before any equity calculation.'}
    annotations = {
        'schema_version': 1,
        'source_plan_sha256': plan_sha,
        'hands': [{'hand_id': row['hand_id'], 'table_id': row['table_id'],
                   'card_review_status': 'ocr_unverified'} for row in rows if row['observations']]}
    # Safety invariant: even perfect OCR confidence cannot enable equity.
    blocked = queue.build(plan, annotations, plan_sha, '0'*64)
    require(blocked['eligible_count'] == 0 and
            blocked['blocked_count'] == len(clips),
            'unsafe OCR promotion to mathematical analysis')
    return worksheet, annotations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan_json')
    parser.add_argument('proposals_json')
    parser.add_argument('new_worksheet_json')
    parser.add_argument('new_annotations_json')
    args = parser.parse_args(argv)
    inputs = [Path(args.plan_json), Path(args.proposals_json)]
    outputs = [Path(args.new_worksheet_json), Path(args.new_annotations_json)]
    require(len({p.resolve() for p in inputs + outputs}) == 4 and
            all(p.suffix == '.json' and p.parent.is_dir() and
                not p.parent.is_symlink() and not p.exists() and
                not p.is_symlink() for p in outputs),
            'outputs must be distinct new JSON files')
    hashes = [queue.digest(p) for p in inputs]
    worksheet, annotations = build(queue.read(inputs[0]), queue.read(inputs[1]),
                                   hashes[0], hashes[1])
    require(hashes == [queue.digest(p) for p in inputs], 'input changed during processing')
    written = []
    try:
        for path, data in zip(outputs, (worksheet, annotations)):
            with path.open('x', encoding='utf-8') as stream:
                written.append(path)
                json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write('\n')
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print(json.dumps({'worksheet': str(outputs[0]), 'annotations': str(outputs[1]),
                      'observations': len(queue.read(inputs[1])['observations']),
                      'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
