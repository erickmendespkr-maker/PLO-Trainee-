"""Offline source-to-ROI pixel audit after independent ingest PTS/hash audit.

Usage: python offline_ingest_roi_pixel_audit.py VIDEO INGEST_DIR NEW_REPORT.json

This checks that sampled JPEG crops visually correspond to decoded source frames,
not just to the dimensions/hash declared in a manifest. It does not identify
cards or actions, reconstruct hands, or authorize equity/EV.

Proof-of-concept limitation: exact-frame redecoding from the start is costly on
long videos; cap checked samples and do not claim 60-minute throughput.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import defaultdict
import io
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageStat

from offline_ingest_pts_audit import audit, decoded_pts, read_manifest, require

MAX_CHECKS = 64
MAX_PNG_BYTES = 40 * 1024 * 1024
MAX_MEAN_ABS_RGB_ERROR = 12.0


def frame_index(pts, actual):
    """Match actual decoded timestamp to the exact frame within 2 ms."""
    i = bisect_left(pts, actual)
    candidates = [j for j in (i - 1, i) if 0 <= j < len(pts)]
    require(candidates, 'no source frame near timestamp')
    idx = min(candidates, key=lambda j: abs(pts[j] - actual))
    require(abs(pts[idx] - actual) <= .002, 'source frame PTS mismatch')
    return idx


def decode_frame(video, index):
    """Decode the frame at absolute index, preserving source pixel geometry."""
    require(type(index) is int and 0 <= index < 250_000, 'invalid frame index')
    try:
        result = subprocess.run([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-i', str(video), '-map', '0:v:0',
            '-vf', f'select=eq(n\\,{index})', '-vsync', '0',
            '-frames:v', '1', '-an', '-sn', '-dn',
            '-f', 'image2pipe', '-vcodec', 'png', '-'],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
            check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('source frame re-decode unavailable/timed out') from exc
    require(result.returncode == 0 and 0 < len(result.stdout) <= MAX_PNG_BYTES,
            'source frame re-decode failed or oversized')
    with Image.open(io.BytesIO(result.stdout)) as img:
        require(img.format == 'PNG', 'unexpected re-decoded frame format')
        return img.convert('RGB').copy()


def mean_rgb_error(reference, observed):
    require(reference.size == observed.size, 'crop dimensions mismatch')
    differences = ImageChops.difference(reference, observed)
    return sum(ImageStat.Stat(differences).mean) / 3


def verify(video_path, ingest_dir):
    video, folder = Path(video_path), Path(ingest_dir)
    provenance = audit(video, folder)  # independent SHA, PTS and geometry audit first
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
    for idx in sorted(grouped):
        source = decode_frame(video, idx)
        for sample in grouped[idx]:
            r = regions[sample['table_id']]
            box = (r['x'], r['y'], r['x'] + r['width'], r['y'] + r['height'])
            require(box[2] <= source.width and box[3] <= source.height,
                    'decoded frame smaller than ROI')
            with Image.open(folder / sample['file']) as jpeg:
                observed = jpeg.convert('RGB')
            error = mean_rgb_error(source.crop(box), observed)
            require(error <= MAX_MEAN_ABS_RGB_ERROR,
                    'ROI pixel mismatch with independently decoded source frame')
            results.append({'table_id': sample['table_id'], 'file': sample['file'],
                            'source_frame_index': idx,
                            'decoded_pts_seconds': pts[idx],
                            'mean_abs_rgb_error': round(error, 4),
                            'visual_roi_match_within_tolerance': True})
    require(len(results) == provenance['sample_count'], 'incomplete ROI comparison')
    # Recheck the original source at the end (audit already checks at its end).
    from offline_ingest_pts_audit import digest
    require(digest(video) == provenance['source_sha256'], 'source changed during pixel audit')
    return {'schema_version': 1,
            'status': 'offline_sampled_roi_pixels_compared_not_ocr',
            'source_sha256': provenance['source_sha256'],
            'tables': provenance['table_count'],
            'samples_checked': len(results),
            'unique_source_frames_decoded': len(grouped),
            'max_mean_abs_rgb_error_allowed': MAX_MEAN_ABS_RGB_ERROR,
            'results': sorted(results, key=lambda x: (x['table_id'], x['file'])),
            'ocr_verified': False, 'hands_reconstructed': False,
            'equity_ev_authorized': False,
            'limitations': [
                'Pixel similarity does not prove table identity, card values, or action OCR.',
                'JPEG compression introduces nonzero error; a tolerant match is not exact identity.',
                'Only sampled frames are checked; unobserved hand transitions may be missed.',
                'Exact-frame FFmpeg decoding may be slow for long recordings; throughput unmeasured.',
                'Requires a human-labeled authorized recording for accuracy evaluation.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('ingest_directory')
    parser.add_argument('new_report_json')
    args = parser.parse_args(argv)
    output = Path(args.new_report_json)
    require(output.suffix.lower() == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists() and
            not output.is_symlink(), 'report must be a new JSON file')
    result = verify(args.recording, args.ingest_directory)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'tables': result['tables'],
                      'samples_checked': result['samples_checked']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
