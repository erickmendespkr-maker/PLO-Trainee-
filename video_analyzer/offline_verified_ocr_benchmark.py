"""Bind offline OCR-label agreement to actual video bytes and verified table crops.

CLI: python offline_verified_ocr_benchmark.py VIDEO BUNDLE OCR_REPORT GOLD NEW_REPORT

Diagnostic only: neither OCR text nor supplied labels authorize hand reconstruction,
equity, EV, clip selection, or claims of real-video accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

import offline_four_table_ocr_benchmark_bridge as bridge

SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_VIDEO_BYTES = 4 * 1024**3
MAX_DURATION = 3600
MAX_SAMPLES = 8
MAX_CROPS = 32
PTS_SLACK = 0.12
SOURCE_STATUS = 'unverified_four_table_region_samples_for_manual_review_only'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_file(path, *, max_bytes):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= max_bytes, 'unsafe or oversized input file')
    return path


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def video_metadata(path, *, ffprobe='ffprobe'):
    require(path.suffix.lower() in {'.mp4', '.webm'}, 'unsupported recording extension')
    try:
        process = subprocess.run(
            [ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
             '-show_entries', 'format=duration,start_time:stream=codec_type,width,height,start_time',
             '-of', 'json', '-i', str(path.resolve())],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('ffprobe unavailable or timed out') from exc
    require(process.returncode == 0 and len(process.stdout) < 200000,
            'ffprobe rejected recording')
    try:
        obj = json.loads(process.stdout)
        videos = [s for s in obj['streams'] if s['codec_type'] == 'video']
        require(len(videos) == 1, 'expected one video stream')
        stream = videos[0]
        duration = float(obj['format']['duration'])
        origin = float(stream.get('start_time', obj['format'].get('start_time', 0)))
        width, height = int(stream['width']), int(stream['height'])
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError('invalid video metadata') from exc
    require(math.isfinite(duration) and 0.05 <= duration <= MAX_DURATION and
            math.isfinite(origin) and -60 <= origin <= MAX_DURATION and
            0 < width <= 8192 and 0 < height <= 8192,
            'recording outside allowed bounds')
    return {'duration_seconds': duration, 'source_pts_origin_seconds': origin,
            'width': width, 'height': height}


def png_dimensions(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    require(len(header) == 24 and header[:16] ==
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR', 'invalid PNG header')
    width = int.from_bytes(header[16:20], 'big')
    height = int.from_bytes(header[20:24], 'big')
    require(0 < width <= 8192 and 0 < height <= 8192, 'invalid PNG size')
    return width, height


def validate_bundle(bundle, recording_hash, metadata):
    root = Path(bundle)
    require(root.is_dir() and not root.is_symlink(), 'invalid bundle directory')
    manifest_path = safe_file(root / 'region_samples.json', max_bytes=1024*1024)
    source = bridge.load(manifest_path)
    require(type(source) is dict and type(source.get('schema_version')) is int and
            source.get('schema_version') == 1 and
            source.get('analysis_status') == SOURCE_STATUS and
            source.get('recording_sha256') == recording_hash and
            source.get('timestamp_semantics') ==
            'decoded_source_pts_seconds_from_ffmpeg_showinfo' and
            all(source.get(flag) is False for flag in (
                'regions_human_confirmed', 'cards_actions_verified',
                'hand_boundaries_verified', 'ready_for_equity_or_ev',
                'automatic_clip_selection_authorized')),
            'source manifest missing provenance or unsafe flags')
    require(finite(source.get('recording_duration_seconds')) and
            abs(source['recording_duration_seconds'] - metadata['duration_seconds']) <= 0.15 and
            source.get('frame_width') == metadata['width'] and
            source.get('frame_height') == metadata['height'] and
            type(source.get('regions')) is list and
            1 <= len(source['regions']) <= 4 and
            type(source.get('samples')) is list and
            1 <= len(source['samples']) <= MAX_SAMPLES,
            'source dimensions or table/sample counts invalid')
    regions = {}
    for region in source['regions']:
        require(type(region) is dict and
                all(type(region.get(k)) is int for k in
                    ('table_id', 'x', 'y', 'width', 'height')),
                'invalid region')
        table = region['table_id']
        require(1 <= table <= 4 and table not in regions and
                min(region['x'], region['y']) >= 0 and
                min(region['width'], region['height']) > 0 and
                region['x'] + region['width'] <= metadata['width'] and
                region['y'] + region['height'] <= metadata['height'],
                'invalid table bounds')
        regions[table] = region
    for a in regions.values():
        for b in regions.values():
            if a['table_id'] >= b['table_id']:
                continue
            require(not (a['x'] < b['x'] + b['width'] and
                         b['x'] < a['x'] + a['width'] and
                         a['y'] < b['y'] + b['height'] and
                         b['y'] < a['y'] + a['height']),
                    'overlapping table regions')
    expected = {}
    files = [(manifest_path, sha(manifest_path))]
    prev_requested = -1.0
    for index, sample in enumerate(source['samples']):
        require(type(sample) is dict, 'invalid sample')
        pts, requested = (sample.get('decoded_source_pts_seconds'),
                          sample.get('requested_seek_seconds'))
        require(finite(pts) and finite(requested) and
                0 <= requested < metadata['duration_seconds'] and
                requested > prev_requested and
                metadata['source_pts_origin_seconds'] - PTS_SLACK <= pts <=
                metadata['source_pts_origin_seconds'] + metadata['duration_seconds'] + PTS_SLACK,
                'sample timestamp outside video')
        prev_requested = requested
        require(type(sample.get('table_crops')) is list and
                len(sample['table_crops']) == len(regions), 'missing table crops')
        frame_rel = f'frames/frame_{index:02d}.png'
        require(sample.get('frame_path') == frame_rel and
                type(sample.get('frame_sha256')) is str and
                SHA.fullmatch(sample['frame_sha256']), 'invalid source frame')
        frame = safe_file(root / frame_rel, max_bytes=16*1024*1024)
        require(png_dimensions(frame) == (metadata['width'], metadata['height']) and
                sha(frame) == sample['frame_sha256'], 'source frame mismatch')
        files.append((frame, sample['frame_sha256']))
        seen_tables = set()
        for crop in sample['table_crops']:
            require(type(crop) is dict and type(crop.get('table_id')) is int and
                    crop['table_id'] in regions and crop['table_id'] not in seen_tables,
                    'invalid table crop identity')
            table = crop['table_id']
            seen_tables.add(table)
            rel = f'tables/table_{table:02d}_sample_{index:02d}.png'
            require(crop.get('path') == rel and
                    type(crop.get('sha256')) is str and SHA.fullmatch(crop['sha256']) and
                    crop.get('width') == regions[table]['width'] and
                    crop.get('height') == regions[table]['height'],
                    'crop metadata mismatch')
            image = safe_file(root / rel, max_bytes=16*1024*1024)
            require(png_dimensions(image) == (crop['width'], crop['height']) and
                    sha(image) == crop['sha256'], 'crop pixels/hash mismatch')
            files.append((image, crop['sha256']))
            expected[(table, index)] = (pts, rel, crop['sha256'], crop['width'], crop['height'])
    require(len(expected) <= MAX_CROPS, 'too many table crops')
    return source, expected, files


def verify_ocr(source, ocr, expected):
    predictions, _, _ = bridge.adapt(ocr)
    require(ocr['recording_sha256'] == source['recording_sha256'] and
            ocr['source_region_samples_sha256'] == source['_manifest_sha256'],
            'OCR source manifest or recording hash mismatch')
    for c in ocr['candidates']:
        key = (c['table_id'], c['sample_index'])
        require(key in expected, 'OCR candidate references missing table/sample')
        pts, path, digest, width, height = expected[key]
        require(abs(c['decoded_source_pts_seconds'] - pts) <= 1e-6 and
                c['source_crop_path'] == path and c['source_crop_sha256'] == digest,
                'OCR evidence path/hash/timestamp mismatch')
        roi = c.get('roi')
        require(type(roi) is dict and
                all(type(roi.get(k)) is int for k in ('x','y','width','height')) and
                roi['x'] >= 0 and roi['y'] >= 0 and
                8 <= roi['width'] <= 2048 and 8 <= roi['height'] <= 2048 and
                roi['x'] + roi['width'] <= width and
                roi['y'] + roi['height'] <= height,
                'invalid OCR ROI bounds')
    return predictions


def verify_labels(labels, expected, *, tolerance_seconds):
    require(type(labels) is list, 'invalid human labels')
    for row in labels:
        require(type(row) is dict and type(row.get('table_id')) is int and
                type(row.get('field')) is str and finite(row.get('timestamp')),
                'invalid label identity')
        require(any(table == row['table_id'] and
                    abs(row['timestamp'] - pts) <= tolerance_seconds
                    for (table, _), (pts, _, _, _, _) in expected.items()),
                'human label not aligned with a sampled table timestamp')


def run(video_path, bundle_path, ocr_path, labels_path, output_path, *,
        tolerance_seconds=0.5, ffprobe='ffprobe'):
    require(finite(tolerance_seconds) and 0 <= tolerance_seconds <= 30,
            'invalid timestamp tolerance')
    video = safe_file(video_path, max_bytes=MAX_VIDEO_BYTES)
    bundle = Path(bundle_path)
    ocr = safe_file(ocr_path, max_bytes=bridge.MAX_BYTES)
    labels = safe_file(labels_path, max_bytes=bridge.MAX_BYTES)
    output = Path(output_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(),
            'output must be new in an existing directory')
    require(len({str(p.resolve()) for p in (video, ocr, labels, output)}) == 4 and
            not output.resolve().is_relative_to(bundle.resolve()),
            'input/output path collision')
    initial = {p: sha(p) for p in (video, ocr, labels)}
    metadata = video_metadata(video, ffprobe=ffprobe)
    source, expected, bundle_files = validate_bundle(bundle, initial[video], metadata)
    source['_manifest_sha256'] = sha(bundle / 'region_samples.json')
    ocr_data, gold = bridge.load(ocr), bridge.load(labels)
    verify_ocr(source, ocr_data, expected)
    verify_labels(gold, expected, tolerance_seconds=tolerance_seconds)
    result = bridge.build(ocr_data, gold, initial[ocr], initial[labels],
                          tolerance_seconds=tolerance_seconds)
    require(all(sha(p) == digest for p, digest in bundle_files) and
            all(sha(p) == digest for p, digest in initial.items()),
            'source changed during benchmark')
    result.update({'status': 'offline_ocr_agreement_with_video_and_crop_hashes_verified',
                   'recording_sha256_verified_against_bytes': initial[video],
                   'source_region_samples_sha256_verified': source['_manifest_sha256'],
                   'recording_metadata_ffprobe': metadata,
                   'source_crop_hashes_verified': len(expected),
                   'candidate_crop_pts_and_roi_bound': True,
                   'human_labels_authenticity_verified': False,
                   'real_video_ocr_accuracy_verified': False,
                   'hands_reconstructed': False,
                   'ready_for_equity_or_ev': False,
                   'automatic_clip_selection_authorized': False,
                   'warning': 'Hash and timestamp agreement do not prove OCR or labels correct.'})
    with tempfile.TemporaryDirectory(prefix='.plo_verified_ocr_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'report.json'
        staged.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                     allow_nan=False) + '\n', encoding='utf-8')
        require(all(sha(p) == digest for p, digest in bundle_files) and
                all(sha(p) == digest for p, digest in initial.items()),
                'source changed before publication')
        os.link(staged, output)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('recording')
    p.add_argument('region_sample_bundle')
    p.add_argument('original_ocr_report')
    p.add_argument('human_labels')
    p.add_argument('new_report')
    p.add_argument('--tolerance-seconds', type=float, default=0.5)
    args = p.parse_args(argv)
    report = run(args.recording, args.region_sample_bundle, args.original_ocr_report,
                 args.human_labels, args.new_report,
                 tolerance_seconds=args.tolerance_seconds)
    print(json.dumps({'labeled': report['summary']['labeled'],
                      'correct': report['summary']['correct'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
