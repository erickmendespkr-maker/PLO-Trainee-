"""Offline, asynchronous recording preflight and sampled table-region evidence.

Usage: python offline_video_ingest_probe.py recording.mp4 regions.json new_output_dir
Regions: {"tables":[{"table_id":1,"x":0,"y":0,"width":320,"height":180}]}
No OCR, poker service, live capture, or decision advice. Inputs are never modified.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MAX_BYTES = 30 * 1024**3
MAX_DURATION = 3600.0
MAX_PIXELS = 3840 * 2160
SAFE_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def command(argv, timeout=45):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              check=False, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Media command failed or timed out') from exc
    require(proc.returncode == 0, 'Media command failed: ' + proc.stderr[-500:])
    return proc.stdout


def probe(recording):
    raw = command(['ffprobe', '-v', 'error', '-show_entries',
                   'format=duration:stream=index,codec_type,width,height,avg_frame_rate',
                   '-of', 'json', str(recording)])
    try:
        data = json.loads(raw)
        duration = float(data['format']['duration'])
        videos = [s for s in data['streams'] if s.get('codec_type') == 'video']
        require(len(videos) == 1, 'Expected exactly one video stream')
        video = videos[0]
        width, height = int(video['width']), int(video['height'])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ValueError('Unsupported or incomplete media metadata') from exc
    require(math.isfinite(duration) and 0.5 <= duration <= MAX_DURATION,
            'Recording duration must be 0.5–3600 seconds')
    require(64 <= width <= 3840 and 64 <= height <= 2160 and
            width * height <= MAX_PIXELS, 'Invalid video dimensions')
    return {'duration_seconds': duration, 'width': width, 'height': height,
            'frame_rate_reported': video.get('avg_frame_rate', 'unknown')}


def regions_from_json(path, width, height):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= 8192, 'Invalid region configuration')
    config = json.loads(path.read_text('utf-8'), object_pairs_hook=no_duplicates)
    require(type(config) is dict and set(config) == {'tables'} and
            type(config['tables']) is list and 1 <= len(config['tables']) <= 4,
            'Expected one to four table regions')
    regions, ids = [], set()
    for region in config['tables']:
        require(type(region) is dict and set(region) ==
                {'table_id', 'x', 'y', 'width', 'height'}, 'Invalid region fields')
        require(all(type(region[k]) is int for k in region), 'Regions require integer pixels')
        table_id, x, y, w, h = (region[k] for k in
                                 ('table_id', 'x', 'y', 'width', 'height'))
        require(1 <= table_id <= 4 and table_id not in ids, 'Duplicate/invalid table ID')
        require(x >= 0 and y >= 0 and w >= 64 and h >= 64 and
                x + w <= width and y + h <= height and
                all(v % 2 == 0 for v in (x, y, w, h)),
                'Table outside frame or not chroma-aligned')
        require(all(x + w <= prior['x'] or prior['x'] + prior['width'] <= x or
                    y + h <= prior['y'] or prior['y'] + prior['height'] <= y
                    for prior in regions), 'Overlapping table regions')
        ids.add(table_id)
        regions.append(region)
    return sorted(regions, key=lambda r: r['table_id'])


def nominal_fps(frame_rate):
    """Nominal rate is only a scheduling hint; decoded PTS remains authoritative."""
    try:
        fps = float(Fraction(str(frame_rate)))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return fps if math.isfinite(fps) and 0 < fps <= 240 else None


def sample_times(duration, frame_rate=None, interval_seconds=30.0):
    """Sparse periodic evidence plus anchors, aligned to nominal frame slots.

    This is NOT hand-boundary detection. Alignment is only approximate for VFR.
    """
    require(type(interval_seconds) in (int, float) and
            math.isfinite(interval_seconds) and 5 <= interval_seconds <= 120,
            'Invalid sampling interval')
    if duration < 1.5:
        requested = [duration / 2]
    else:
        requested = [0.25, duration / 2, duration - 0.25]
    if duration >= 60:
        requested.extend(i * interval_seconds for i in
                         range(1, math.ceil(duration / interval_seconds))
                         if i * interval_seconds < duration)
    fps = nominal_fps(frame_rate)
    if fps:
        # Avoid seeking after the last nominal frame on 1 fps recordings.
        last_nominal = max(0.0, math.floor((duration - 1e-6) * fps) / fps)
        requested = [math.floor((min(t, last_nominal) + 1e-8) * fps) / fps
                     for t in requested]
    return sorted({round(max(0.0, min(t, duration - 1e-6)), 3)
                   for t in requested})


def extract_sample_frame(recording, crop, timestamp, target, frame_rate):
    """Decode one frame and record its actual PTS; retry earlier for sparse FPS."""
    fps = nominal_fps(frame_rate)
    backoff = max(0.5, 1.0 / fps) if fps else 2.0
    seeks = list(dict.fromkeys([timestamp, max(0.0, timestamp - backoff), 0.0]))
    for attempt, seek in enumerate(seeks, 1):
        target.unlink(missing_ok=True)
        try:
            proc = subprocess.run(
                ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info',
                 '-copyts', '-ss', str(round(seek, 6)), '-i', str(recording),
                 '-map', '0:v:0', '-vf', crop + ',showinfo', '-frames:v', '1',
                 '-q:v', '3', '-an', '-sn', '-dn', '-y', str(target)],
                capture_output=True, text=True, check=False, timeout=90,
                stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('Media command failed or timed out') from exc
        pts = re.findall(r'\bpts_time:([-+]?\d+(?:\.\d+)?)', proc.stderr)
        if proc.returncode == 0 and target.is_file() and target.stat().st_size > 0 and pts:
            actual = float(pts[0])
            require(math.isfinite(actual), 'Nonfinite decoded timestamp')
            return {'actual_frame_timestamp_seconds': actual,
                    'seek_timestamp_seconds': round(seek, 6),
                    'seek_attempts': attempt}
    target.unlink(missing_ok=True)
    raise ValueError('Could not decode sampled frame, including sparse-FPS fallback')


def build(recording, region_config, output_dir, interval_seconds=30.0):
    recording, region_config, output_dir = map(Path, (recording, region_config, output_dir))
    require(recording.is_file() and not recording.is_symlink() and
            recording.suffix.lower() in SAFE_EXTENSIONS and
            0 < recording.stat().st_size <= MAX_BYTES, 'Invalid recording')
    require(output_dir.parent.is_dir() and not output_dir.exists() and
            not output_dir.is_symlink() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
            'Output must be a new safe directory')
    require(len({str(p.resolve()) for p in (recording, region_config, output_dir)}) == 3,
            'Paths must differ')
    media = probe(recording)
    regions = regions_from_json(region_config, media['width'], media['height'])
    recording_hash, regions_hash = sha256(recording), sha256(region_config)
    times = sample_times(media['duration_seconds'], media['frame_rate_reported'],
                         interval_seconds)
    with tempfile.TemporaryDirectory(prefix='.plo_ingest_', dir=output_dir.parent) as tmp:
        stage = Path(tmp)
        frames = []
        for r in regions:
            for idx, timestamp in enumerate(times):
                name = f'table_{r["table_id"]:02d}_sample_{idx:03d}.jpg'
                target = stage / name
                crop = f'crop={r["width"]}:{r["height"]}:{r["x"]}:{r["y"]}'
                decoded = extract_sample_frame(recording, crop, timestamp, target,
                                               media['frame_rate_reported'])
                frames.append({'table_id': r['table_id'], 'timestamp_seconds': timestamp,
                               **decoded, 'file': name, 'sha256': sha256(target)})

        manifest = {
            'schema_version': 1,
            'analysis_status': 'offline_sampled_video_preflight_no_ocr',
            'source_sha256': recording_hash, 'regions_config_sha256': regions_hash,
            'source_size_bytes': recording.stat().st_size,
            'media': media, 'regions': regions, 'samples': frames,
            'sampling_interval_seconds': interval_seconds,
            'sampling_method': 'periodic_and_anchors_nominal_fps_aligned',
            'timestamps_note': 'timestamp_seconds is requested; actual_frame_timestamp_seconds is decoded PTS; VFR may differ',
            'video_evidence_interpreted': False, 'hands_reconstructed': False,
            'equity_ev_computed': False, 'live_poker_integration': False,
            'warning': 'Quadros de amostra nao validam cartas, maos, acoes ou EV.'
        }
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2,
                                            ensure_ascii=False, allow_nan=False) + '\n', 'utf-8')
        require(sha256(recording) == recording_hash and
                sha256(region_config) == regions_hash,
                'Inputs changed during extraction')
        require(not output_dir.exists(), 'Output path appeared during processing')
        os.rename(stage, output_dir)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('regions_json')
    parser.add_argument('new_output_dir')
    parser.add_argument('--interval-seconds', type=float, default=30.0)
    args = parser.parse_args(argv)
    manifest = build(args.recording, args.regions_json, args.new_output_dir,
                     interval_seconds=args.interval_seconds)
    print(json.dumps({'tables': len(manifest['regions']),
                      'samples': len(manifest['samples']),
                      'duration_seconds': manifest['media']['duration_seconds']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
