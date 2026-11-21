"""Audit offline MP4 export integrity without inferring poker decisions."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def audit_clip(clip, source=None):
    clip = Path(clip)
    sidecar = Path(str(clip) + '.json')
    if not clip.is_file() or not sidecar.is_file() or clip.is_symlink() or sidecar.is_symlink():
        raise ValueError('clip and sidecar must be regular files')
    if sidecar.stat().st_size > 65536:
        raise ValueError('oversized sidecar')
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError('duplicate JSON key')
            out[k] = v
        return out
    report = json.loads(sidecar.read_text(encoding='utf-8'), object_pairs_hook=unique,
                        parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    if not isinstance(report, dict) or report.get('clip_sha256') != digest(clip):
        raise ValueError('clip SHA-256 mismatch')
    if report.get('analysis_status') != 'manually_selected_offline_clip':
        raise ValueError('unexpected analysis status')
    if report.get('automatic_clip_selection_authorized') is not False or report.get('video_evidence_verified') is not False:
        raise ValueError('unverified video cannot be promoted')
    start, end = report.get('start_seconds'), report.get('end_seconds')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
        raise ValueError('invalid timestamps')
    if source is not None and digest(source) != report.get('source_video_sha256'):
        raise ValueError('source SHA-256 mismatch')
    command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(clip)]
    decoded = json.loads(subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout)
    video = next((s for s in decoded.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not video:
        raise ValueError('no video stream')
    crop = report.get('crop')
    if not isinstance(crop, dict) or any(type(crop.get(k)) is not int for k in ('width', 'height')):
        raise ValueError('invalid crop evidence')
    if (video.get('width'), video.get('height')) != (crop['width'], crop['height']):
        raise ValueError('clip dimensions mismatch')
    duration = float(decoded['format']['duration'])
    expected = end - start
    if not math.isfinite(duration) or not 0 < duration or abs(duration - expected) > 0.25:
        raise ValueError('clip duration mismatch')
    return {'verified': True, 'clip_sha256': digest(clip), 'source_checked': source is not None,
            'clip_duration_seconds': duration, 'strategic_analysis_verified': False}
