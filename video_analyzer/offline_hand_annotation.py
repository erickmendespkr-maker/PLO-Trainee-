"""Validate human annotations linked to offline evidence; never infer missing cards/actions."""
import hashlib
import json
import math
from pathlib import Path

RANKS = set('23456789TJQKA')
SUITS = set('cdhs')
STREETS = {'preflop', 'flop', 'turn', 'river'}
ACTIONS = {'fold', 'check', 'call', 'bet', 'raise'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _cards(cards, count):
    if not isinstance(cards, list) or len(cards) > count:
        raise ValueError('invalid card count')
    for card in cards:
        if not isinstance(card, str) or len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
            raise ValueError('invalid card')
    if len(set(cards)) != len(cards):
        raise ValueError('duplicate cards')


def validate_annotations(bundle, annotations):
    if not isinstance(bundle, dict) or bundle.get('status') != 'UNREVIEWED_EVIDENCE_REVIEW_BUNDLE':
        raise ValueError('unsupported evidence bundle')
    digest = bundle.get('evidence_json_sha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid evidence digest')
    if not isinstance(annotations, dict) or annotations.get('evidence_json_sha256') != digest:
        raise ValueError('evidence digest mismatch')
    hands = annotations.get('hands')
    if not isinstance(hands, list):
        raise ValueError('hands must be list')
    observed = set()
    output = []
    for hand in hands:
        if not isinstance(hand, dict):
            raise ValueError('invalid hand')
        table = hand.get('table_id')
        hand_id = hand.get('hand_id')
        if not isinstance(table, str) or not table or not isinstance(hand_id, str) or not hand_id:
            raise ValueError('missing identifiers')
        if hand.get('human_confirmed', False) not in (True, False) or type(hand.get('human_confirmed', False)) is not bool:
            raise ValueError('invalid human confirmation')
        for flag in ('equity_ev_verified', 'gto_verified', 'cards_visually_verified', 'actions_visually_verified'):
            if hand.get(flag) is True:
                raise ValueError('unsupported verification claim')
        key = (table, hand_id)
        if key in observed:
            raise ValueError('duplicate hand')
        observed.add(key)
        start, end = hand.get('start_seconds'), hand.get('end_seconds')
        if not _number(start) or not _number(end) or start >= end:
            raise ValueError('invalid interval')
        variant = hand.get('variant')
        if variant not in ('PLO5', 'PLO6'):
            raise ValueError('invalid variant')
        hole, board = hand.get('hero_cards', []), hand.get('board_cards', [])
        _cards(hole, 5 if variant == 'PLO5' else 6)
        _cards(board, 5)
        if set(hole) & set(board):
            raise ValueError('card collision')
        actions = hand.get('actions', [])
        if not isinstance(actions, list):
            raise ValueError('invalid actions')
        last = start
        for action in actions:
            if not isinstance(action, dict) or action.get('action') not in ACTIONS or action.get('street') not in STREETS:
                raise ValueError('invalid action')
            t = action.get('seconds')
            if not _number(t) or t < last or t > end:
                raise ValueError('action out of order/range')
            last = t
            amount = action.get('amount')
            if amount is not None and not _number(amount):
                raise ValueError('invalid amount')
        status = 'HUMAN_REVIEWED_PARTIAL'
        if hand.get('human_confirmed') is True and len(hole) == (5 if variant == 'PLO5' else 6):
            status = 'HUMAN_REVIEWED_CARDS_ONLY'
        output.append({'table_id': table, 'hand_id': hand_id, 'variant': variant,
                       'start_seconds': start, 'end_seconds': end, 'status': status,
                       'hero_cards': hole, 'board_cards': board, 'actions': actions,
                       'equity_ev_verified': False, 'gto_verified': False})
    return {'status': 'HUMAN_ANNOTATION_VALIDATION_ONLY', 'evidence_json_sha256': digest,
            'hands': output, 'equity_ev_verified': False, 'gto_verified': False}


def write_annotations(bundle_path, annotations_path, output_path):
    paths = [Path(p) for p in (bundle_path, annotations_path, output_path)]
    if any(p.is_symlink() for p in paths) or len({p.resolve() for p in paths}) != 3:
        raise ValueError('unsafe paths')
    result = validate_annotations(json.loads(paths[0].read_text()), json.loads(paths[1].read_text()))
    with paths[2].open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result
