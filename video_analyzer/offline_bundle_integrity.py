"""Read-only audit of an exported offline MP4 and its JSON sidecar.

Integrity checks never establish visual correctness or strategic accuracy.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess


def verify_bundle(clip_path, *, ffprobe='ffprobe', tolerance_s=0.25):
    if isinstance(tolerance_s, bool) or not isinstance(tolerance_s, (int, float)) or not math.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError('invalid tolerance')
    clip = Path(clip_path)
    report_path = clip.with_suffix('.json')
    if not clip.is_file() or not report_path.is_file():
        return {'status': 'INVALID', 'problems': ['missing_clip_or_report'], 'visual_verification': False}
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError):
        return {'status': 'INVALID', 'problems': ['invalid_json'], 'visual_verification': False}
    if not isinstance(report, dict) or not isinstance(report.get('clip'), dict):
        return {'status': 'INVALID', 'problems': ['invalid_schema'], 'visual_verification': False}
    info = report['clip']
    problems = []
    expected = info.get('sha256')
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        problems.append('missing_or_invalid_hash')
    else:
        digest = hashlib.sha256()
        with open(clip, 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != expected:
            problems.append('clip_hash_mismatch')
    duration = info.get('actual_duration_s')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        problems.append('invalid_reported_duration')
    else:
        try:
            result = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(clip)],
                                    capture_output=True, text=True, check=True)
            actual = float(json.loads(result.stdout)['format']['duration'])
            if not math.isfinite(actual) or actual <= 0 or abs(actual - duration) > tolerance_s:
                problems.append('duration_mismatch')
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            problems.append('ffprobe_failed')
    return {'status': 'INTEGRITY_OK_TEMPORAL_ONLY' if not problems else 'INVALID',
            'problems': problems, 'visual_verification': False}
