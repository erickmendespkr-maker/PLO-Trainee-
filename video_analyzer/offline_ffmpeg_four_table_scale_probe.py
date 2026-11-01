"""Bounded synthetic FFmpeg four-quadrant extraction benchmark (NOT OCR).

Generate an artificial 1-fps MP4, seek into four manually defined quadrants,
verify decoded PTS and pixel identity, and measure elapsed time, disk and
Linux child-process RSS high-water. No real recordings or poker decisions.

Usage: python offline_ffmpeg_four_table_scale_probe.py NEW_REPORT.json --seconds 2400 --interval 600
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
try:
    import resource  # Unix-only; absent on Windows
except ImportError:
    resource = None
import shutil
import subprocess
import tempfile
import time

from PIL import Image

STATUS = 'synthetic_four_quadrant_ffmpeg_only_not_real_video_validation'
REGIONS = (
    (1, 0, 0, 'red'), (2, 160, 0, 'green'),
    (3, 0, 120, 'blue'), (4, 160, 120, 'yellow'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(args, timeout=180):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg command unavailable or timed out') from exc
    require(result.returncode == 0, 'FFmpeg failed: ' + result.stderr[-400:].decode('utf-8', 'replace'))
    return result


def sample_times(seconds, interval):
    require(type(seconds) is int and 8 <= seconds <= 3600, 'seconds must be integer 8..3600')
    require(type(interval) is int and 2 <= interval <= 1200, 'interval must be integer 2..1200')
    times = sorted(set([0, seconds - 2] + list(range(interval, seconds - 1, interval))))
    require(len(times) <= 24, 'At most 24 sample timestamps (96 ROI images)')
    return times


def fixture(path, seconds):
    boxes = ','.join(f'drawbox=x={x}:y={y}:w=160:h=120:color={color}:t=fill'
                     for _, x, y, color in REGIONS)
    command(['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error', '-f', 'lavfi',
             '-i', f'color=c=black:s=320x240:r=1:d={seconds}', '-vf', boxes,
             '-an', '-c:v', 'mpeg4', '-g', '12', '-q:v', '7', '-pix_fmt', 'yuv420p',
             '-f', 'mp4', str(path)], timeout=180)
    require(path.is_file() and 0 < path.stat().st_size < 100 * 1024 * 1024,
            'Synthetic fixture missing or oversized')


def is_expected_color(rgb, color):
    r, g, b = rgb
    return {
        'red': r > 160 and g < 100 and b < 100,
        'green': g > 75 and r < 100 and b < 100,
        'blue': b > 150 and r < 100 and g < 100,
        'yellow': r > 160 and g > 120 and b < 100,
    }[color]


def crop_and_check(video, target, timestamp, region):
    table_id, x, y, color = region
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'info',
           '-copyts', '-ss', str(timestamp), '-i', str(video), '-map', '0:v:0',
           '-vf', f'crop=160:120:{x}:{y},showinfo', '-frames:v', '1',
           '-an', '-sn', '-dn', '-f', 'image2', '-vcodec', 'png', str(target)]
    result = command(cmd, timeout=45)
    match = re.search(rb'\bpts_time:([-+]?\d+(?:\.\d+)?)', result.stderr)
    require(match is not None, 'No decoded PTS from FFmpeg showinfo')
    pts = float(match.group(1))
    require(math.isfinite(pts) and abs(pts - timestamp) <= 1.01,
            'Decoded PTS outside one frame of requested timestamp')
    with Image.open(target) as image:
        require(image.size == (160, 120), 'Incorrect cropped region dimensions')
        rgb = image.convert('RGB').getpixel((80, 60))
    require(is_expected_color(rgb, color), f'Table {table_id} crop pixels incorrect')
    return {'table_id': table_id, 'requested_seconds': timestamp,
            'decoded_pts_seconds': pts, 'roi_color_test': 'passed',
            'image_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'image_size_bytes': target.stat().st_size}


def benchmark(*, seconds=120, interval=30):
    times = sample_times(seconds, interval)
    require(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and FFprobe required')
    ffmpeg_version = command(['ffmpeg', '-version'], 10).stdout.decode('utf-8', 'replace').splitlines()[0]
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='plo_four_table_synthetic_') as directory:
        root = Path(directory)
        video = root / 'synthetic_4_quadrants.mp4'
        t0 = time.perf_counter()
        fixture(video, seconds)
        fixture_elapsed = time.perf_counter() - t0
        probe = command(['ffprobe', '-v', 'error', '-show_entries',
                         'format=duration:stream=width,height', '-of', 'json', str(video)], 20)
        media = json.loads(probe.stdout)
        require(len(media['streams']) == 1 and media['streams'][0]['width'] == 320 and
                media['streams'][0]['height'] == 240 and
                abs(float(media['format']['duration']) - seconds) <= 1.01,
                'Fixture metadata mismatch')
        video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        samples = []
        t1 = time.perf_counter()
        for timestamp in times:
            for region in REGIONS:
                target = root / f'table_{region[0]}_t_{timestamp}.png'
                samples.append(crop_and_check(video, target, timestamp, region))
        extract_elapsed = time.perf_counter() - t1
        require(hashlib.sha256(video.read_bytes()).hexdigest() == video_sha,
                'Fixture mutated during extraction')
        crop_bytes = sum(item['image_size_bytes'] for item in samples)
        fixture_bytes = video.stat().st_size
    # Linux ru_maxrss is a child-process HIGH-WATER MARK, not total memory usage.
    child_rss_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss if resource is not None and os.name == 'posix' else None
    return {'schema_version': 1, 'status': STATUS, 'ffmpeg_version': ffmpeg_version,
            'fixture': {'duration_seconds': seconds, 'fps': 1, 'resolution': [320, 240],
                        'codec': 'mpeg4', 'sha256': video_sha, 'size_bytes': fixture_bytes},
            'table_count': 4, 'samples_per_table': len(times), 'sample_timestamps': times,
            'total_crops': len(samples), 'crop_bytes_total': crop_bytes,
            'fixture_generation_seconds': round(fixture_elapsed, 6),
            'roi_extraction_seconds': round(extract_elapsed, 6),
            'total_wall_seconds': round(time.perf_counter() - start, 6),
            'linux_child_peak_rss_kib_high_water': child_rss_kib,
            'all_crops_verified': True, 'samples': samples,
            'real_video_verified': False, 'ocr_verified': False,
            'hand_reconstruction_verified': False, 'equity_ev_authorized': False,
            'limitations': ['Solid-color 320x240 MPEG-4 at 1 fps is not a poker recording.',
                            'Four quadrants are manually known, not automatically detected.',
                            'PTS tolerance is one synthetic frame; VFR not covered.',
                            'RSS is maximum child high-water, not total process peak.',
                            'Results depend on host, codec, resolution, storage and CPU.',
                            'No OCR, hand detection, equity or EV was performed.']}


def write_new(report, target):
    target = Path(target)
    require(target.suffix == '.json' and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink(), 'Output must be a new JSON file')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_report_json')
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--interval', type=int, default=30)
    args = parser.parse_args(argv)
    write_new(benchmark(seconds=args.seconds, interval=args.interval), args.new_report_json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
