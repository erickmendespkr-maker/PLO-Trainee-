"""Deterministic, append-only offline evidence ledger (not a poker verdict)."""
import hashlib
import json
import math


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def append_event(events, event):
    if not isinstance(events, list) or not isinstance(event, dict):
        raise ValueError('invalid ledger input')
    if set(event) != {'video_sha256', 'hand_id', 'table_id', 'pts_seconds', 'kind', 'payload'}:
        raise ValueError('invalid event schema')
    if not isinstance(event['video_sha256'], str) or len(event['video_sha256']) != 64 or any(c not in '0123456789abcdef' for c in event['video_sha256']):
        raise ValueError('invalid video hash')
    if not isinstance(event['hand_id'], str) or not event['hand_id'] or not isinstance(event['table_id'], int) or isinstance(event['table_id'], bool) or not 1 <= event['table_id'] <= 4:
        raise ValueError('invalid hand/table')
    pts = event['pts_seconds']
    if type(pts) not in (float, int) or not math.isfinite(pts) or pts < 0:
        raise ValueError('invalid timestamp')
    if event['kind'] not in ('ocr_proposal', 'human_correction', 'model_hypothesis', 'clip_request') or not isinstance(event['payload'], dict):
        raise ValueError('invalid event type')
    if event['kind'] == 'ocr_proposal' and event['payload'].get('confirmed') is True:
        raise ValueError('OCR cannot self-confirm')
    previous = events[-1]['entry_sha256'] if events else '0' * 64
    if events and not verify(events):
        raise ValueError('broken existing ledger')
    record = {'sequence': len(events), 'previous_sha256': previous, 'event': event}
    record['entry_sha256'] = hashlib.sha256(canonical(record).encode()).hexdigest()
    return events + [record]


def verify(events):
    if not isinstance(events, list):
        return False
    previous = '0' * 64
    for index, item in enumerate(events):
        if not isinstance(item, dict) or set(item) != {'sequence', 'previous_sha256', 'event', 'entry_sha256'}:
            return False
        if item['sequence'] != index or item['previous_sha256'] != previous:
            return False
        unsigned = {key: item[key] for key in ('sequence', 'previous_sha256', 'event')}
        try:
            digest = hashlib.sha256(canonical(unsigned).encode()).hexdigest()
        except (TypeError, ValueError):
            return False
        if item['entry_sha256'] != digest:
            return False
        previous = digest
    return True
