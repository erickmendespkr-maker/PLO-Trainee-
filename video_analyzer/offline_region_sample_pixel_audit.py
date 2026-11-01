"""Fail-closed, source-video pixel audit of offline_four_table_sample_review PNGs.

CLI: python offline_region_sample_pixel_audit.py VIDEO BUNDLE NEW_REPORT.json
This is diagnostic evidence integrity, never card/action recognition or EV approval.
"""
from __future__ import annotations

from bisect import bisect_left
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageChops

from offline_verified_ocr_benchmark import (safe_file, sha, video_metadata,
                                            validate_bundle, require)

MAX_FRAMES = 250_000
MAX_DECODED_BYTES = 160 * 1024 * 1024


def frame_pts(video, *, ffprobe='ffprobe'):
    try:
        proc = subprocess.run(
            [ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
             '-select_streams', 'v:0', '-show_entries',
             'frame=best_effort_timestamp_time', '-of', 'csv=p=0',
             '-i', str(video.resolve())], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('ffprobe frame timestamps unavailable') from exc
    require(proc.returncode == 0 and len(proc.stdout) < 5_000_000,
            'ffprobe frame timestamp output invalid or too large')
    try:
        pts = [float(line.strip().split(',')[0]) for line in proc.stdout.splitlines()
               if line.strip()]
    except ValueError as exc:
        raise ValueError('invalid decoded frame timestamp') from exc
    require(1 <= len(pts) <= MAX_FRAMES and
            all(math.isfinite(p) for p in pts) and
            all(a < b for a, b in zip(pts, pts[1:])),
            'frame timestamps missing, nonfinite or nonmonotonic')
    return pts


def frame_index(pts, timestamp):
    require(type(timestamp) in (int, float) and math.isfinite(timestamp),
            'invalid source PTS')
    i = bisect_left(pts, timestamp)
    candidates = [j for j in (i-1, i) if 0 <= j < len(pts)]
    require(candidates, 'no frame at requested PTS')
    best = min(candidates, key=lambda j: abs(pts[j] - timestamp))
    require(abs(pts[best] - timestamp) <= 0.002,
            'source PTS not found in independent ffprobe timeline')
    return best


def _same_pixels(left, right):
    with Image.open(left) as a, Image.open(right) as b:
        require(a.format == b.format == 'PNG' and a.size == b.size,
                'source frame PNG format/dimensions mismatch')
        return ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is None


def _crop_matches(source, crop, region):
    with Image.open(source) as image, Image.open(crop) as observed:
        require(image.format == observed.format == 'PNG', 'invalid PNG image')
        x, y, w, h = (region[k] for k in ('x', 'y', 'width', 'height'))
        actual = image.convert('RGB').crop((x, y, x+w, y+h))
        require(actual.size == observed.size, 'table crop geometry mismatch')
        return ImageChops.difference(actual, observed.convert('RGB')).getbbox() is None


def run(video_path, bundle_path, output_path, *, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    video = safe_file(video_path, max_bytes=4 * 1024**3)
    root, output = Path(bundle_path), Path(output_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            not output.resolve().is_relative_to(root.resolve()),
            'report must be new and outside source bundle')
    before = sha(video)
    metadata = video_metadata(video, ffprobe=ffprobe)
    source, expected, files = validate_bundle(root, before, metadata)
    require(1 <= len(source['samples']) <= 8 and len(expected) <= 32,
            'source sample budget exceeded')
    pts = frame_pts(video, ffprobe=ffprobe)
    indices = [frame_index(pts, s['decoded_source_pts_seconds'])
               for s in source['samples']]
    require(len(set(indices)) == len(indices), 'duplicate decoded source frame')
    expression = '+'.join(f'eq(n\\,{i})' for i in sorted(indices))
    with tempfile.TemporaryDirectory(prefix='.plo_region_pixels_', dir=output.parent) as tmp:
        stage = Path(tmp)
        pattern = str(stage / 'decoded_%02d.png')
        try:
            proc = subprocess.run([
                ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                '-noautorotate', '-i', str(video.resolve()), '-map', '0:v:0',
                '-vf', f'select={expression}', '-fps_mode', 'passthrough',
                '-frames:v', str(len(indices)), '-an', '-sn', '-dn',
                '-c:v', 'png', '-start_number', '0', '-f', 'image2', pattern],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=300,
                check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('FFmpeg independent source replay failed') from exc
        require(proc.returncode == 0, 'FFmpeg independent source replay rejected recording')
        decoded = sorted(stage.glob('decoded_*.png'))
        require(len(decoded) == len(indices) and
                sum(p.stat().st_size for p in decoded) <= MAX_DECODED_BYTES,
                'decoded source frames missing or over budget')
        by_index = dict(zip(sorted(indices), decoded))
        regions = {r['table_id']: r for r in source['regions']}
        checks = []
        for sample_id, sample in enumerate(source['samples']):
            original = root / sample['frame_path']
            independent = by_index[indices[sample_id]]
            require(_same_pixels(original, independent),
                    'source frame pixels do not match independently decoded recording')
            for crop in sample['table_crops']:
                require(_crop_matches(original, root / crop['path'],
                                      regions[crop['table_id']]),
                        'table crop pixels do not match source frame region')
                checks.append({'table_id': crop['table_id'], 'sample_index': sample_id,
                               'frame_index': indices[sample_id],
                               'source_pts_seconds': pts[indices[sample_id]],
                               'source_frame_pixels_exact': True,
                               'table_crop_pixels_exact': True})
        require(len(checks) == len(expected) and sha(video) == before and
                all(sha(path) == digest for path, digest in files),
                'evidence changed during pixel audit')
        report = {'schema_version': 1,
                  'status': 'offline_region_samples_source_pixels_verified',
                  'recording_sha256': before,
                  'region_samples_sha256': sha(root / 'region_samples.json'),
                  'samples_verified': len(indices), 'table_crops_verified': len(checks),
                  'source_frames_independently_decoded': len(indices),
                  'checks': checks,
                  'real_poker_recognition_verified': False,
                  'hands_reconstructed': False,
                  'ready_for_equity_or_ev': False,
                  'automatic_clip_selection_authorized': False,
                  'warning': 'Pixel integrity is not recognition accuracy or manual approval.'}
        staged = stage / 'report.json'
        staged.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', 'utf-8')
        require(sha(video) == before and
                all(sha(path) == digest for path, digest in files),
                'evidence changed before publication')
        os.link(staged, output)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('bundle')
    parser.add_argument('new_report')
    args = parser.parse_args()
    result = run(args.recording, args.bundle, args.new_report)
    print(json.dumps({'samples': result['samples_verified'],
                      'crops': result['table_crops_verified'],
                      'ready_for_equity_or_ev': False}))
