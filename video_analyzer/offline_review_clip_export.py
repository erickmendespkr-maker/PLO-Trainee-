"""Fail-closed offline clip exporter with audit sidecar; no poker conclusions."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
try:
    from .offline_clip_evidence_gate import classify_clip_evidence
except ImportError:
    from offline_clip_evidence_gate import classify_clip_evidence

class ClipExportError(ValueError):
    pass

def _sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def export_review_clip(source, destination, record, *, ffmpeg='ffmpeg', ffprobe='ffprobe', timeout=180):
    """Export a local recorded interval; preserve source and clip SHA in JSON."""
    src, dst = Path(source), Path(destination)
    if not src.is_file() or not src.stat().st_size:
        raise ClipExportError('source video missing or empty')
    if src.resolve() == dst.resolve():
        raise ClipExportError('source and destination must differ')
    if dst.suffix.lower() != '.mp4':
        raise ClipExportError('destination must be MP4')
    if dst.exists() or dst.with_suffix('.json').exists():
        raise ClipExportError('refusing to overwrite existing artifacts')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ClipExportError('invalid timeout')
    gate = classify_clip_evidence(record)
    probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'json', str(src)], capture_output=True, text=True,
                           timeout=timeout, check=True)
    try:
        duration = float(json.loads(probe.stdout)['format']['duration'])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ClipExportError('video duration unavailable') from exc
    if not math.isfinite(duration) or duration <= 0 or gate['end_pts'] > duration + 0.001:
        raise ClipExportError('clip interval outside source duration')
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.clip-', dir=dst.parent) as tmp:
        video_tmp = Path(tmp) / 'clip.mp4'
        side_tmp = Path(tmp) / 'clip.json'
        subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error',
                        '-y', '-ss', str(gate['start_pts']), '-i', str(src),
                        '-t', str(gate['end_pts'] - gate['start_pts']),
                        '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264',
                        '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-movflags', '+faststart', str(video_tmp)],
                       capture_output=True, text=True, timeout=timeout, check=True)
        if not video_tmp.is_file() or not video_tmp.stat().st_size:
            raise ClipExportError('ffmpeg produced empty video')
        manifest = {
            'schema_version': 1, 'source_sha256': _sha256(src),
            'clip_sha256': _sha256(video_tmp),
            'source_duration_seconds': duration,
            'requested_interval_seconds': [gate['start_pts'], gate['end_pts']],
            'table_id': gate['table_id'], 'evidence_gate': gate,
            'ev_is_conditional': True, 'gto_solution': False,
            'human_review_of_export': False,
            'explanation': 'No hand-specific mathematical conclusion is embedded in this clip.',
        }
        side_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        if dst.exists() or dst.with_suffix('.json').exists():
            raise ClipExportError('output appeared during export')
        os.replace(video_tmp, dst)
        try:
            os.replace(side_tmp, dst.with_suffix('.json'))
        except Exception:
            dst.unlink(missing_ok=True)
            raise
    return manifest
