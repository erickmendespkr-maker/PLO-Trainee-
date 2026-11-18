"""Read-only verification of reviewed offline MP4 exports and JSON sidecars.

Verifies file integrity and timestamps, NOT accuracy of poker reconstruction.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def audit_export(clip, sidecar=None, source=None):
    """Return an audit report; raise ValueError for invalid or mismatched artifacts."""
    clip = Path(clip)
    sidecar = Path(sidecar) if sidecar is not None else Path(str(clip) + '.json')
    if any(not p.is_file() or p.is_symlink() for p in (clip, sidecar)) or clip.suffix.lower() != '.mp4':
        raise ValueError('missing or unsafe export artifact')
    try:
        meta = json.loads(sidecar.read_text(encoding='utf8'))
    except (ValueError, UnicodeError, OSError) as exc:
        raise ValueError('invalid JSON sidecar') from exc
    if not isinstance(meta, dict) or meta.get('schema_version') != 1:
        raise ValueError('unsupported sidecar')
    for key in ('source_sha256', 'plan_sha256', 'clip_sha256'):
        val = meta.get(key)
        if not isinstance(val, str) or len(val) != 64 or any(c not in '0123456789abcdef' for c in val):
            raise ValueError('invalid hash field: ' + key)
    if meta['clip_sha256'] != _sha(clip):
        raise ValueError('MP4 SHA-256 mismatch')
    start, end, claimed = (meta.get(k) for k in ('start_pts', 'end_pts', 'clip_duration_seconds'))
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end, claimed)):
        raise ValueError('invalid timestamps')
    if not 0 <= start < end or claimed <= 0 or end - start > 180:
        raise ValueError('invalid interval')
    if type(meta.get('table_id')) is not int or not 1 <= meta['table_id'] <= 4:
        raise ValueError('invalid table')
    if not isinstance(meta.get('hand_id'), str) or not meta['hand_id'].strip():
        raise ValueError('invalid hand id')
    if not isinstance(meta.get('reviewed_explanation'), str) or not meta['reviewed_explanation'].strip():
        raise ValueError('missing reviewed explanation')
    if meta.get('conditional_model_only') is not True or meta.get('not_gto') is not True or meta.get('audio_included') is not False:
        raise ValueError('missing model/export safeguards')
    try:
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(clip)],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=30, check=True)
        duration = float(json.loads(p.stdout)['format']['duration'])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('unable to probe MP4 duration') from exc
    if not math.isfinite(duration) or abs(duration - claimed) > .25 or abs(duration - (end - start)) > .25:
        raise ValueError('MP4 duration mismatch')
    source_checked = source is not None
    if source_checked:
        source = Path(source)
        if not source.is_file() or source.is_symlink() or _sha(source) != meta['source_sha256']:
            raise ValueError('source SHA-256 mismatch')
    return {'status': 'MEDIA_PROVENANCE_VERIFIED', 'clip_sha256': meta['clip_sha256'],
            'source_checked': source_checked, 'table_id': meta['table_id'],
            'hand_id': meta['hand_id'], 'duration_seconds': duration,
            'strategy_validated': False, 'human_review_independently_verified': False}
