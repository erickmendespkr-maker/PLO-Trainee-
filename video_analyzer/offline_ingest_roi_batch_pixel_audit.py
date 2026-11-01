"""Bounded, batched source-frame ROI pixel verification for offline recordings.

This is a drop-in alternative to offline_ingest_roi_pixel_audit.verify. It
independently audits crop SHA, dimensions and PTS, then decodes each distinct
selected source frame in one ordered FFmpeg pass (instead of one full replay
per source frame). No OCR, hand reconstruction, equity or EV is authorized.

PNG frames are written to a private temporary directory, verified and removed.
The bounded spot-check limit remains 64 crops; this is not a 60-minute video
throughput guarantee. Video inputs are read-only.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

from offline_ingest_pts_audit import audit, decoded_pts, digest, read_manifest, require
from offline_ingest_roi_pixel_audit import (MAX_CHECKS, MAX_MEAN_ABS_RGB_ERROR,
                                            MAX_PNG_BYTES, frame_index,
                                            mean_rgb_error)

MAX_TOTAL_PNG_BYTES = 512 * 1024 * 1024


def decode_selected_frames(video, indices, expected_size):
    """Return ordered (frame index, RGB image) pairs from one FFmpeg decode pass.

    Only callers with a bounded list of already-audited indices may invoke this.
    A temporary output directory is removed even on a failed FFmpeg invocation.
    """
    require(type(indices) is list and 1 <= len(indices) <= MAX_CHECKS and
            all(type(i) is int and 0 <= i < 250_000 for i in indices) and
            indices == sorted(set(indices)), 'invalid selected frame indices')
    require(type(expected_size) is tuple and len(expected_size) == 2 and
            all(type(x) is int and 64 <= x <= 3840 for x in expected_size) and
            expected_size[0] * expected_size[1] <= 3840 * 2160,
            'invalid expected source dimensions')
    expression = '+'.join(f'eq(n\\,{i})' for i in indices)
    with tempfile.TemporaryDirectory(prefix='plo_batch_pixels_') as tmp:
        pattern = str(Path(tmp) / 'frame_%03d.png')
        try:
            result = subprocess.run([
                'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                '-i', str(video), '-map', '0:v:0', '-vf', f'select={expression}',
                '-fps_mode', 'passthrough', '-frames:v', str(len(indices)),
                '-an', '-sn', '-dn', '-c:v', 'png', '-start_number', '0',
                '-f', 'image2', pattern], stdin=subprocess.DEVNULL,
                capture_output=True, timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('batched source re-decode unavailable/timed out') from exc
        require(result.returncode == 0, 'batched source re-decode failed: ' +
                result.stderr.decode('utf-8', 'replace')[-300:])
        paths = sorted(Path(tmp).glob('frame_*.png'))
        require(len(paths) == len(indices) and
                [p.name for p in paths] ==
                [f'frame_{i:03d}.png' for i in range(len(indices))],
                'batched source frame count mismatch')
        total = 0
        for idx, path in zip(indices, paths):
            require(path.is_file() and not path.is_symlink(), 'invalid decoded PNG')
            size = path.stat().st_size
            total += size
            require(0 < size <= MAX_PNG_BYTES and total <= MAX_TOTAL_PNG_BYTES,
                    'batched decoded PNGs exceed size budget')
            with Image.open(path) as png:
                require(png.format == 'PNG' and png.size == expected_size,
                        'batched source PNG geometry mismatch')
                source = png.convert('RGB')
                source.load()
                yield idx, source


def verify(video_path, ingest_dir):
    """Independently audit evidence then compare crops to batched source frames."""
    video, folder = Path(video_path), Path(ingest_dir)
    provenance = audit(video, folder)
    require(provenance['sample_count'] <= MAX_CHECKS,
            'too many samples for bounded source pixel verification')
    manifest = read_manifest(folder / 'manifest.json')
    regions = {r['table_id']: r for r in manifest['regions']}
    samples = {s['file']: s for s in manifest['samples']}
    pts = decoded_pts(video)
    grouped = defaultdict(list)
    for checked in provenance['verified_samples']:
        sample = samples[checked['file']]
        idx = frame_index(pts, sample['actual_frame_timestamp_seconds'])
        grouped[idx].append(sample)
    results = []
    for idx, source in decode_selected_frames(
            video, sorted(grouped), (manifest['media']['width'],
                                     manifest['media']['height'])):
        for sample in grouped[idx]:
            region = regions[sample['table_id']]
            box = (region['x'], region['y'], region['x'] + region['width'],
                   region['y'] + region['height'])
            require(box[2] <= source.width and box[3] <= source.height,
                    'decoded frame smaller than ROI')
            with Image.open(folder / sample['file']) as jpeg:
                observed = jpeg.convert('RGB')
                observed.load()
            error = mean_rgb_error(source.crop(box), observed)
            require(error <= MAX_MEAN_ABS_RGB_ERROR,
                    'ROI pixel mismatch with independently decoded source frame')
            results.append({'table_id': sample['table_id'], 'file': sample['file'],
                            'source_frame_index': idx,
                            'decoded_pts_seconds': pts[idx],
                            'mean_abs_rgb_error': round(error, 4),
                            'visual_roi_match_within_tolerance': True})
    require(len(results) == provenance['sample_count'], 'incomplete ROI comparison')
    require(digest(video) == provenance['source_sha256'],
            'source changed during batched pixel audit')
    return {'schema_version': 1,
            'status': 'offline_sampled_roi_pixels_compared_not_ocr',
            'source_sha256': provenance['source_sha256'],
            'tables': provenance['table_count'],
            'samples_checked': len(results),
            'unique_source_frames_decoded': len(grouped),
            'decoder_strategy': 'single_ffmpeg_select_pass_bounded_png_files',
            'ffmpeg_decode_passes': 1,
            'max_mean_abs_rgb_error_allowed': MAX_MEAN_ABS_RGB_ERROR,
            'results': sorted(results, key=lambda x: (x['table_id'], x['file'])),
            'ocr_verified': False, 'hands_reconstructed': False,
            'equity_ev_authorized': False,
            'limitations': [
                'Only a bounded spot-check of ROI pixels, not full video recognition.',
                'Pixel similarity is not proof of card/action identity or OCR correctness.',
                'JPEG compression requires a tolerance; frames may be visually similar.',
                'One FFmpeg decode pass still scans to the last selected frame.',
                'High-resolution or long recordings need separate throughput benchmarks.',
                'Requires an authorized human-labeled recording to measure accuracy.']}
