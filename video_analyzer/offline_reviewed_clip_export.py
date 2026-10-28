"""Offline FFmpeg single-table clip exporter with source hash and explanation sidecar.

Explicitly reviewer-selected timestamps and crop only. Does not select decisions,
read poker platforms, verify OCR, or assert the selected hand is complete.

Usage: python offline_reviewed_clip_export.py VIDEO.mp4 REQUEST.json NEW_CLIP.mp4
Writes NEW_CLIP.mp4 and NEW_CLIP.mp4.json. No audio is exported in this MVP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

MAX_REQUEST_BYTES = 64 * 1024
MAX_VIDEO_BYTES = 8 * 1024 ** 3
MAX_DURATION = 5400.0


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def probe(video):
    cmd = ['ffprobe', '-v', 'error', '-show_entries',
           'format=duration:stream=codec_type,width,height',
           '-of', 'json', str(video)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=30, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Cannot probe local video') from exc
    raw = json.loads(completed.stdout)
    streams = [s for s in raw.get('streams', []) if s.get('codec_type') == 'video']
    require(len(streams) >= 1, 'No video stream')
    width, height = streams[0].get('width'), streams[0].get('height')
    duration = float(raw.get('format', {}).get('duration', 'nan'))
    require(type(width) is int and type(height) is int and
            width >= 2 and height >= 2 and
            0 < duration <= MAX_DURATION, 'Invalid video dimensions/duration')
    return width, height, duration


def validate_request(req, width, height, duration, video_sha):
    require(type(req) is dict and set(req) == {
        'schema_version', 'hand_id', 'table_id', 'start_seconds', 'end_seconds',
        'crop', 'explanation', 'source_video_sha256', 'reviewer_confirmed_offline',
    }, 'Invalid request schema')
    require(type(req['schema_version']) is int and req['schema_version'] == 1,
            'Unsupported schema')
    require(type(req['hand_id']) is str and 1 <= len(req['hand_id'].strip()) <= 128,
            'Missing hand ID')
    require(type(req['table_id']) is int and 1 <= req['table_id'] <= 4,
            'Table must be 1..4')
    require(req['reviewer_confirmed_offline'] is True, 'Human approval required')
    require(type(req['source_video_sha256']) is str and
            req['source_video_sha256'] == video_sha, 'Video SHA-256 mismatch')
    require(type(req['explanation']) is str and
            1 <= len(req['explanation'].strip()) <= 1000,
            'Explanation required')
    for key in ('start_seconds', 'end_seconds'):
        require(type(req[key]) in (int, float) and
                0 <= req[key] <= MAX_DURATION, 'Invalid timestamps')
    start, end = float(req['start_seconds']), float(req['end_seconds'])
    require(start < end <= duration and 0.1 <= end - start <= 180,
            'Clip outside video or duration limit')
    crop = req['crop']
    require(type(crop) is dict and set(crop) == {'x', 'y', 'width', 'height'},
            'Crop rectangle required')
    require(all(type(v) is int and v >= 0 for v in crop.values()),
            'Crop must contain nonnegative integers')
    x, y, w, h = (crop[k] for k in ('x', 'y', 'width', 'height'))
    require(w >= 2 and h >= 2 and all(v % 2 == 0 for v in (x, y, w, h)) and
            x + w <= width and y + h <= height, 'Invalid even-pixel crop')
    return start, end, x, y, w, h


def export(video_path, request_path, output_path):
    video, request, output = map(Path, (video_path, request_path, output_path))
    report = Path(str(output) + '.json')
    require(video.is_file() and not video.is_symlink() and
            0 < video.stat().st_size <= MAX_VIDEO_BYTES and
            video.suffix.lower() in ('.mp4', '.webm'), 'Invalid local recording')
    require(request.is_file() and not request.is_symlink() and
            0 < request.stat().st_size <= MAX_REQUEST_BYTES, 'Invalid request file')
    require(output.suffix.lower() == '.mp4' and output.parent.is_dir() and
            not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            not report.exists() and not report.is_symlink(),
            'Output clip and report must not exist')
    require(len({video.resolve(), request.resolve(), output.resolve(), report.resolve()}) == 4,
            'Input/output paths must be distinct')
    video_sha, request_sha = digest(video), digest(request)
    raw = json.loads(request.read_text(encoding='utf-8'),
                     object_pairs_hook=lambda pairs: _unique_keys(pairs),
                     parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    width, height, duration = probe(video)
    start, end, x, y, w, h = validate_request(raw, width, height, duration, video_sha)
    with tempfile.TemporaryDirectory(prefix='plo_clip_', dir=output.parent) as d:
        stage = Path(d) / 'clip.mp4'
        cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
               '-ss', f'{start:.6f}', '-i', str(video), '-t', f'{end-start:.6f}',
               '-map', '0:v:0', '-an', '-vf', f'crop={w}:{h}:{x}:{y}',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(stage)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError('FFmpeg export failed') from exc
        require(stage.is_file() and stage.stat().st_size > 0, 'No exported clip')
        require(digest(video) == video_sha and digest(request) == request_sha,
                'Input changed during export')
        meta = {'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
                'hand_id': raw['hand_id'], 'table_id': raw['table_id'],
                'start_seconds': start, 'end_seconds': end, 'crop': raw['crop'],
                'explanation': raw['explanation'], 'source_video_sha256': video_sha,
                'source_request_sha256': request_sha, 'clip_sha256': digest(stage),
                'audio_included': False, 'video_evidence_verified': False,
                'automatic_clip_selection_authorized': False,
                'warning': 'Timestamp and crop are manually supplied, not independently validated as a poker hand.'}
        meta_stage = Path(d) / 'clip.json'
        meta_stage.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n',
                              encoding='utf-8')
        os.link(stage, output)
        try:
            os.link(meta_stage, report)
        except OSError:
            output.unlink(missing_ok=True)
            raise
    return meta


def _unique_keys(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, 'Duplicate JSON key')
        out[k] = v
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video'); p.add_argument('request'); p.add_argument('new_clip')
    a = p.parse_args(argv)
    r = export(a.video, a.request, a.new_clip)
    print(json.dumps({'status': r['analysis_status'], 'clip_sha256': r['clip_sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
