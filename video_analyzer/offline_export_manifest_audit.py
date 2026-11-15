"""Verify the actual offline_review_clip_export sidecar (not a poker verdict)."""
import hashlib
import json
import math
import subprocess
from pathlib import Path


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def audit_export(mp4_path, *, ffprobe='ffprobe', tolerance_seconds=0.35):
    mp4 = Path(mp4_path)
    sidecar = mp4.with_suffix('.json')
    for path in (mp4, sidecar):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError('missing or unsafe artifact')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(sidecar.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if type(data) is not dict or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('invalid manifest schema')
    if data.get('gto_solution') is not False or data.get('human_review_of_export') is not False or data.get('ev_is_conditional') is not True:
        raise ValueError('invalid review or strategy status')
    if data.get('explanation') != 'No hand-specific mathematical conclusion is embedded in this clip.':
        raise ValueError('unsupported explanation')
    digest = data.get('clip_sha256')
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid SHA-256')
    if _digest(mp4) != digest:
        raise ValueError('MP4 hash mismatch')
    interval = data.get('requested_interval_seconds')
    source_duration = data.get('source_duration_seconds')
    if type(interval) is not list or len(interval) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in interval):
        raise ValueError('invalid interval')
    if type(source_duration) not in (int, float) or not math.isfinite(source_duration) or not 0 <= interval[0] < interval[1] <= source_duration + 0.001:
        raise ValueError('interval outside source')
    if type(tolerance_seconds) not in (int, float) or not math.isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise ValueError('invalid tolerance')
    probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(mp4)], capture_output=True, text=True, check=True, timeout=30)
    actual = float(json.loads(probe.stdout)['format']['duration'])
    if not math.isfinite(actual) or abs(actual - (interval[1] - interval[0])) > tolerance_seconds:
        raise ValueError('clip duration mismatch')
    return {'verified_artifacts': True, 'clip_sha256': digest, 'duration_seconds': actual,
            'human_review_required': True, 'strategic_verdict_allowed': False}
