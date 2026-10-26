"""Bounded visual spot-check of a manually exported offline MP4 against its source.

This measures *sampled decoded image similarity*, not frame-exact alignment,
hand/action boundaries, OCR accuracy, or a strategic conclusion. No live input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from offline_manual_clip_export import (digest_file, probe, read_selection,
                                        require, validate_selection)
from offline_clip_frame_pts_audit import source_video_start_pts

SAMPLES = 3
PIXELS = 32 * 32
SHIFTS = (-0.12, 0.0, 0.12)
MAX_REPORT = 32_768


def _frame(path, second, crop=None):
    """Decode one bounded 32x32 grayscale frame using accurate FFmpeg seeking.

    Seeking/decoding may select a nearby frame; this function does not expose
    the decoded frame's actual PTS, so the report must not assert exact PTS.
    """
    require(type(second) in (int, float) and math.isfinite(second) and second >= 0,
            'Invalid sample timestamp')
    filters = []
    if crop:
        filters.append(f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}")
    filters.append('scale=32:32:flags=area')
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
           '-ss', f'{second:.6f}', '-i', str(path), '-map', '0:v:0',
           '-an', '-sn', '-vf', ','.join(filters), '-frames:v', '1',
           '-pix_fmt', 'gray', '-f', 'rawvideo', '-']
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=45)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ValueError(f'FFmpeg sample failed: {type(exc).__name__}') from exc
    require(len(result.stdout) == PIXELS, 'Missing or unexpected decoded frame')
    return result.stdout


def _difference(a, b):
    require(len(a) == len(b) == PIXELS, 'Invalid decoded frame size')
    return round(sum(abs(x - y) for x, y in zip(a, b)) / (PIXELS * 255), 6)


def build_report(source_path, clip_path, sidecar, *, source_sha, clip_sha):
    source, clip = Path(source_path), Path(clip_path)
    require(type(sidecar) is dict and sidecar.get('schema_version') == 1 and
            sidecar.get('status') == 'manual_clip_not_video_hand_verified',
            'Expected manual clip sidecar')
    for flag in ('source_pts_boundaries_verified', 'hand_reconstruction_verified',
                 'math_analysis_linked', 'strategic_error_established',
                 'automatic_clip_selection_authorized'):
        require(sidecar.get(flag) is False, 'Unexpected verification flag')
    sel = validate_selection(sidecar.get('selection'))
    require(sel['recording_sha256'] == source_sha and
            sidecar.get('source_sha256') == source_sha and
            sidecar.get('output_sha256') == clip_sha,
            'Source or clip SHA-256 mismatch')
    source_meta, clip_meta = probe(source), probe(clip)
    require(abs(source_video_start_pts(source)) <= .05 and
            abs(source_video_start_pts(clip)) <= .05,
            'Nonzero video PTS origin unsupported')
    duration = sel['end_seconds'] - sel['start_seconds']
    require(sel['end_seconds'] <= source_meta['duration_seconds'] + .01 and
            abs(clip_meta['duration_seconds'] - duration) <= .35,
            'Selection and media duration disagree')
    crop = sel['crop']
    if crop:
        require(crop['x'] + crop['width'] <= source_meta['width'] and
                crop['y'] + crop['height'] <= source_meta['height'] and
                (clip_meta['width'], clip_meta['height']) == (crop['width'], crop['height']),
                'Clip crop geometry mismatch')
    else:
        require((clip_meta['width'], clip_meta['height']) ==
                (source_meta['width'], source_meta['height']), 'Clip geometry mismatch')

    offsets = [min(duration - .05, max(.05, duration * fraction))
               for fraction in (.1, .5, .9)]
    require(len(set(offsets)) == SAMPLES and duration > .2,
            'Clip too short for visual spot-check')
    samples = []
    for offset in offsets:
        out_frame = _frame(clip, offset)
        expected = sel['start_seconds'] + offset
        candidates = []
        for shift in SHIFTS:
            second = max(0.0, min(source_meta['duration_seconds'] - .01, expected + shift))
            source_frame = _frame(source, second, crop)
            candidates.append({'requested_source_second': round(second, 6),
                               'nominal_shift_seconds': shift,
                               'normalized_gray_mae': _difference(source_frame, out_frame)})
        best = min(candidates, key=lambda item: item['normalized_gray_mae'])
        samples.append({'requested_clip_second': round(offset, 6),
                        'nominal_source_second': round(expected, 6),
                        'best_candidate': best, 'candidates': candidates,
                        'clip_decoded_gray_sha256': hashlib.sha256(out_frame).hexdigest()})
    return {
        'schema_version': 1,
        'status': 'sampled_visual_similarity_only_not_pts_or_hand_verified',
        'source_sha256': source_sha, 'clip_sha256': clip_sha,
        'selection_sha256': hashlib.sha256(json.dumps(sel, sort_keys=True,
                         separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
        'table_id_human_selected': sel['table_id'],
        'samples': samples,
        'mean_best_normalized_gray_mae': round(sum(s['best_candidate']['normalized_gray_mae']
                                                     for s in samples) / len(samples), 6),
        'sampling_method': 'three requested clip offsets; each compared to three nearby source seeks; 32x32 gray',
        'actual_decoded_frame_pts_measured': False,
        'frame_exact_export_verified': False,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'strategic_error_established': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'FFmpeg accurate seek selects nearby decoded frames; actual decoded PTS is not measured here.',
            'Only three spots and three bounded source seeks per spot are compared.',
            'Similar or static images can match despite incorrect temporal alignment.',
            'Re-encoding, overlays and VFR can alter sampled images or shift frame selection.',
            'Low grayscale MAE is not proof of correct timestamps, poker actions, OCR, equity or EV.',
        ],
    }


def export_report(source_path, clip_path, sidecar_path, output_path):
    source, clip, sidecar, output = map(Path, (source_path, clip_path, sidecar_path, output_path))
    require(len({p.resolve() for p in (source, clip, sidecar, output)}) == 4,
            'Overlapping input/output paths')
    require(all(p.is_file() and not p.is_symlink() for p in (source, clip, sidecar)) and
            output.suffix.lower() == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists(), 'Unsafe input/output path')
    sidecar_raw = sidecar.read_bytes()
    require(len(sidecar_raw) <= 32_768, 'Oversized sidecar')
    data = read_selection(sidecar)
    source_sha, clip_sha = digest_file(source), digest_file(clip)
    report = build_report(source, clip, data, source_sha=source_sha, clip_sha=clip_sha)
    require(sidecar.read_bytes() == sidecar_raw and
            digest_file(source) == source_sha and digest_file(clip) == clip_sha,
            'Input changed during visual audit')
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    require(len(payload) <= MAX_REPORT, 'Report too large')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_mp4')
    parser.add_argument('exported_clip_mp4')
    parser.add_argument('clip_sidecar_json')
    parser.add_argument('new_report_json')
    args = parser.parse_args(argv)
    report = export_report(args.source_mp4, args.exported_clip_mp4,
                           args.clip_sidecar_json, args.new_report_json)
    print(json.dumps({'status': report['status'],
                      'mean_best_normalized_gray_mae': report['mean_best_normalized_gray_mae']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())