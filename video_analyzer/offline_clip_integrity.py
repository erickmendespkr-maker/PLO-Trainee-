"""Offline verification of exported MP4 and sidecar; no poker verdicts."""
import hashlib
import json
import math
from pathlib import Path


def verify_export(mp4_path):
    mp4 = Path(mp4_path)
    if not mp4.is_file() or mp4.is_symlink():
        raise ValueError('missing or unsafe MP4')
    sidecar = Path(str(mp4) + '.json')
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError('missing or unsafe sidecar')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(sidecar.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if type(data) is not dict or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('invalid sidecar schema')
    digest = data.get('clip_sha256')
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid clip hash')
    actual = hashlib.sha256()
    with mp4.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            actual.update(chunk)
    if actual.hexdigest() != digest:
        raise ValueError('MP4 hash mismatch')
    if data.get('strategic_verdict_allowed') is not False or data.get('review_status') not in ('confirmed', 'insufficient_data'):
        raise ValueError('unapproved strategic verdict or review status')
    expected = 'INSUFFICIENT_DATA' if data['review_status'] == 'insufficient_data' else 'CONDITIONAL MODEL ONLY'
    if data.get('annotation') != expected:
        raise ValueError('annotation mismatch')
    for key in ('start_seconds', 'end_seconds', 'actual_clip_duration_seconds'):
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('invalid timestamp')
    if not 0 <= data['start_seconds'] < data['end_seconds'] or data['actual_clip_duration_seconds'] <= 0:
        raise ValueError('invalid interval')
    return {'verified': True, 'clip_sha256': digest, 'review_status': data['review_status'], 'strategic_verdict_allowed': False}
