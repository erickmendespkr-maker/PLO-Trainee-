"""Export an offline reviewed-interval clip with an auditable JSON sidecar.

Temporal alignment does not establish visual or strategic correctness.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess

try:
    from .offline_clip_report_bundle import build_clip_report_bundle
    from .offline_ffmpeg_clip_export import export_review_clip
except ImportError:
    from offline_clip_report_bundle import build_clip_report_bundle
    from offline_ffmpeg_clip_export import export_review_clip


def _duration(path, ffprobe):
    process = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    value = float(json.loads(process.stdout)['format']['duration'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('invalid video duration')
    return value


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def export_review_bundle(source, clip_path, analysis, *, clip_start_s, clip_end_s,
                         ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Reject unaligned intervals and existing outputs; export MP4 and JSON."""
    source, clip_path = Path(source), Path(clip_path)
    report_path = clip_path.with_suffix('.json')
    if not source.is_file() or source.resolve() in (clip_path.resolve(), report_path.resolve()):
        raise ValueError('invalid source or destination')
    if clip_path.suffix.lower() != '.mp4' or clip_path.exists() or report_path.exists():
        raise FileExistsError('output must be new MP4 and JSON paths')
    if not isinstance(analysis, dict):
        raise ValueError('analysis must be a dict')
    duration = _duration(source, ffprobe)
    video_hash = _sha256(source)
    bundle = build_clip_report_bundle(analysis, video_sha256=video_hash,
                                      clip_start_s=clip_start_s, clip_end_s=clip_end_s,
                                      video_duration_s=duration)
    if bundle['alignment']['status'] != 'TEMPORALLY_ALIGNED_ONLY':
        raise ValueError('hand interval not covered by requested clip')
    clip_created = False
    report_created = False
    try:
        result = export_review_clip(source, clip_path, start_s=clip_start_s,
                                    end_s=clip_end_s, ffmpeg=ffmpeg, ffprobe=ffprobe)
        clip_created = True
        report = bundle['report']
        report['clip']['export_status'] = result['status']
        report['clip']['actual_duration_s'] = result['actual_duration_s']
        report['clip']['sha256'] = _sha256(clip_path)
        report['clip']['visually_verified'] = False
        data = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Track ownership immediately after exclusive creation. A concurrent
        # writer's sidecar must never be removed by our exception handler.
        with open(report_path, 'x', encoding='utf-8') as output:
            report_created = True
            output.write(data)
        return {'clip': str(clip_path), 'report': str(report_path),
                'status': report['status'], 'visually_verified': False}
    except Exception:
        if clip_created and clip_path.exists():
            clip_path.unlink()
        if report_created and report_path.exists():
            report_path.unlink()
        raise
