"""Offline-only FFmpeg export of human-reviewed clip plans; no strategic claims.

A READY plan is not proof of a correct hand reconstruction. This exporter
verifies the original bytes, cuts the requested interval, and records provenance.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def command(args, timeout):
    try:
        p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError('media command unavailable or timed out') from e
    if p.returncode:
        raise ValueError('media command failed: ' + p.stderr[-300:].decode('utf8', 'replace'))
    return p.stdout


def export_reviewed_clip(source, plan, destination):
    """Export an accurate re-encoded clip, with separate JSON provenance.

    Output must be a new path. No auto-selection or unreviewed analysis.
    """
    source, destination = Path(source), Path(destination)
    sidecar = Path(str(destination) + '.json')
    if not isinstance(plan, dict) or plan.get('status') != 'READY_FOR_OFFLINE_EXPORT':
        raise ValueError('human-reviewed plan required')
    if plan.get('conditional_model_only') is not True or plan.get('not_gto') is not True or plan.get('requires_source_hash_check') is not True:
        raise ValueError('missing conditional model safeguards')
    start, end = plan.get('start_pts'), plan.get('end_pts')
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in (start, end)) or not 0 <= start < end or end-start > 180:
        raise ValueError('invalid clip timestamps')
    if type(plan.get('table_id')) is not int or not 1 <= plan['table_id'] <= 4:
        raise ValueError('invalid table')
    manifest_hash = plan.get('manifest_sha256')
    payload = {k: v for k, v in plan.items() if k != 'manifest_sha256'}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if manifest_hash != expected:
        raise ValueError('modified clip plan')
    if (not source.is_file() or source.is_symlink() or source.suffix.lower() not in ('.mp4', '.webm')
            or not destination.parent.is_dir() or destination.parent.is_symlink()
            or destination.suffix.lower() != '.mp4' or destination.exists() or sidecar.exists()
            or destination.is_symlink() or sidecar.is_symlink()):
        raise ValueError('unsafe source or destination')
    if digest(source) != plan.get('video_sha256'):
        raise ValueError('recording SHA-256 mismatch')
    probe = json.loads(command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'json', str(source)], 30))
    duration = float(probe['format']['duration'])
    if not math.isfinite(duration) or end > duration + .05:
        raise ValueError('clip exceeds recording')
    with tempfile.TemporaryDirectory(prefix='.plo_export_', dir=destination.parent) as tmp:
        tmpfile = Path(tmp) / 'clip.mp4'
        command(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-ss', str(start),
                 '-t', str(end-start), '-map', '0:v:0', '-an', '-c:v', 'libx264',
                 '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                 str(tmpfile)], 180)
        actual = json.loads(command(['ffprobe', '-v', 'error', '-show_entries',
                                     'format=duration', '-of', 'json', str(tmpfile)], 30))
        clip_duration = float(actual['format']['duration'])
        if abs(clip_duration - (end-start)) > .25:
            raise ValueError('clip duration mismatch')
        if digest(source) != plan['video_sha256']:
            raise ValueError('source changed during export')
        metadata = {'schema_version': 1, 'analysis_status': 'human_reviewed_clip_not_independent_strategy_validation',
                    'source_sha256': plan['video_sha256'], 'plan_sha256': manifest_hash,
                    'clip_sha256': digest(tmpfile), 'table_id': plan['table_id'],
                    'hand_id': plan['hand_id'], 'start_pts': start, 'end_pts': end,
                    'reviewed_explanation': plan['explanation'],
                    'clip_duration_seconds': clip_duration, 'audio_included': False,
                    'conditional_model_only': True, 'not_gto': True,
                    'warning': 'Human review is asserted by plan; not independently verified by exporter.'}
        staged = Path(tmp) / 'clip.json'
        staged.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
        import os
        os.link(tmpfile, destination)
        try:
            os.link(staged, sidecar)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return metadata
