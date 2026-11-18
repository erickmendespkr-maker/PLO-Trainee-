"""Validate offline video observations without promoting OCR proposals to facts."""
import hashlib
import json
import math

FIELDS = frozenset({'hole_cards', 'board', 'pot', 'stack', 'action', 'bet'})


def validate_observations(observations, video_sha256, duration_seconds):
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('invalid video hash')
    if type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError('invalid duration')
    if not isinstance(observations, list):
        raise ValueError('observations must be a list')
    result = []
    seen = set()
    for entry in observations:
        if not isinstance(entry, dict):
            raise ValueError('invalid observation')
        table, pts, field = entry.get('table_id'), entry.get('pts'), entry.get('field')
        if type(table) is not int or not 1 <= table <= 4 or type(pts) not in (int, float) or not math.isfinite(pts) or not 0 <= pts <= duration_seconds:
            raise ValueError('invalid table or PTS')
        if field not in FIELDS:
            raise ValueError('unknown field')
        raw, confidence = entry.get('raw'), entry.get('confidence')
        if not isinstance(raw, str) or len(raw) > 512 or type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('invalid OCR observation')
        roi = entry.get('roi')
        if not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int or v < 0 for v in roi) or roi[2] == 0 or roi[3] == 0:
            raise ValueError('invalid ROI')
        frame_hash = entry.get('frame_sha256')
        if not isinstance(frame_hash, str) or len(frame_hash) != 64 or any(c not in '0123456789abcdef' for c in frame_hash):
            raise ValueError('invalid frame hash')
        key = (table, pts, field, tuple(roi), frame_hash)
        if key in seen:
            raise ValueError('duplicate observation')
        seen.add(key)
        result.append({'table_id': table, 'pts': pts, 'field': field, 'raw': raw, 'confidence': confidence, 'roi': roi[:], 'frame_sha256': frame_hash, 'verified_by_human': False, 'value': None})
    result.sort(key=lambda e: (e['pts'], e['table_id'], e['field'], e['roi']))
    payload = {'schema_version': 1, 'video_sha256': video_sha256, 'duration_seconds': duration_seconds, 'observations': result, 'strategy_validated': False}
    payload['ledger_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return payload
