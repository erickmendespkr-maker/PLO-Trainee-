"""Offline review-only decision gate. No automatic strategic verdicts.

Inputs are manually confirmed evidence records; OCR suggestions alone cannot
establish a poker hand. The output is a structured triage decision, not GTO.
"""
import math
import re

CARD = re.compile(r'^[2-9TJQKA][cdhs]$')
IDENT = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def assess(record):
    if type(record) is not dict or set(record) != {
        'schema_version', 'hand_id', 'variant', 'table_id', 'start_seconds',
        'end_seconds', 'hero_cards', 'board_cards', 'action', 'pot_bb',
        'call_bb', 'field_evidence', 'ranges_assumed', 'source_video_sha256'
    }:
        raise ValueError('invalid review record schema')
    if type(record['schema_version']) is not int or record['schema_version'] != 1:
        raise ValueError('invalid schema version')
    if type(record['hand_id']) is not str or not IDENT.fullmatch(record['hand_id']):
        raise ValueError('invalid hand ID')
    if record['variant'] not in ('PLO5', 'PLO6') or type(record['variant']) is not str:
        raise ValueError('unsupported variant')
    if type(record['table_id']) is not int or not 1 <= record['table_id'] <= 4:
        raise ValueError('invalid table')
    start, end = record['start_seconds'], record['end_seconds']
    if not number(start, 0, 5400) or not number(end, 0, 5400) or not .1 <= end-start <= 180:
        raise ValueError('invalid timestamps')
    if type(record['source_video_sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', record['source_video_sha256']):
        raise ValueError('invalid source hash')
    hero, board = record['hero_cards'], record['board_cards']
    if type(hero) is not list or type(board) is not list:
        raise ValueError('invalid cards')
    if len(hero) not in (0, int(record['variant'][-1])) or not 0 <= len(board) <= 5:
        raise ValueError('incomplete or invalid card count')
    if any(type(c) is not str or not CARD.fullmatch(c) for c in hero+board):
        raise ValueError('invalid card notation')
    if len(set(hero+board)) != len(hero+board):
        raise ValueError('duplicate card')
    if record['action'] not in ('call', 'fold', 'raise', 'unknown') or type(record['action']) is not str:
        raise ValueError('invalid action')
    if not number(record['pot_bb'], 0, 1e6) or not number(record['call_bb'], 0, 1e6):
        raise ValueError('invalid pot/call')
    if type(record['ranges_assumed']) is not bool:
        raise ValueError('invalid ranges flag')
    fields = record['field_evidence']
    required = ('table', 'hand_boundary', 'hero_cards', 'board_cards', 'action', 'pot', 'call')
    if type(fields) is not dict or set(fields) != set(required):
        raise ValueError('invalid evidence fields')
    missing = []
    for key in required:
        item = fields[key]
        if type(item) is not dict or set(item) != {'status', 'confidence', 'timestamp_seconds'}:
            raise ValueError('invalid evidence item')
        if item['status'] not in ('human_confirmed', 'ocr_candidate', 'unknown'):
            raise ValueError('invalid evidence status')
        if not number(item['confidence'], 0, 1) or not number(item['timestamp_seconds'], start, end):
            raise ValueError('invalid evidence confidence/timestamp')
        if item['status'] != 'human_confirmed':
            missing.append(key)
    if not hero:
        missing.append('hero_cards_not_visible')
    if len(board) < 3:
        missing.append('insufficient_board')
    if record['action'] == 'unknown':
        missing.append('action_unknown')
    if record['action'] == 'call' and record['call_bb'] <= 0:
        missing.append('call_cost_missing')
    if not record['ranges_assumed']:
        missing.append('ranges_not_supplied')
    status = 'READY_FOR_CONDITIONAL_MODEL' if not missing else 'INSUFFICIENT_DATA'
    return {'schema_version': 1, 'hand_id': record['hand_id'], 'table_id': record['table_id'],
            'analysis_status': status, 'missing_or_unconfirmed': sorted(set(missing)),
            'source_video_sha256': record['source_video_sha256'],
            'source_hand_reconstruction_verified': False,
            'strategic_error_established': False, 'gto_solution': False,
            'warning': 'Ready means evidence may be modeled under assumed ranges, not that a strategic verdict is proven.'}
