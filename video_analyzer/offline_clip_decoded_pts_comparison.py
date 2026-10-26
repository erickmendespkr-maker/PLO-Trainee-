"""Observe decoded source/clip frame PTS for an offline, human-selected MP4.

This is a bounded *timeline observation*, not a frame-identity check, proof of
hand boundaries, OCR, strategic error, or automatic selection. It uses only
user-supplied local recordings and existing manual-export sidecars.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess

from offline_manual_clip_export import (digest_file, probe, read_selection,
                                        require, validate_selection)
from offline_clip_frame_pts_audit import source_video_start_pts

MAX_SIDECAR_BYTES = 32_768
MAX_PROBE_BYTES = 2_000_000
MAX_FRAMES = 50_000
MAX_REPORT_BYTES = 64_000
MAX_SAMPLES = 11
MAX_WINDOW_SECONDS = 210.0
SIDECAR_FALSE_FLAGS = (
    'source_pts_boundaries_verified', 'hand_reconstruction_verified',
    'math_analysis_linked', 'strategic_error_established',
    'automatic_clip_selection_authorized',
)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def decoded_pts(path, begin, span):
    """Decode timestamp metadata from an FFprobe read_intervals sample.

    FFprobe seeks approximately to a keyframe. This is NOT a guarantee that
    every source frame in the requested window was examined.
    """
    require(_finite(begin) and _finite(span) and begin >= 0 and
            0 < span <= MAX_WINDOW_SECONDS, 'Invalid bounded PTS interval')
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
           '-read_intervals', f'{begin:.6f}%+{span:.6f}', '-show_frames',
           '-show_entries', 'frame=best_effort_timestamp_time',
           '-of', 'csv=p=0', str(path)]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=90)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        raise ValueError(f'FFprobe decoded-frame sampling failed: {type(exc).__name__}') from exc
    require(0 < len(proc.stdout) <= MAX_PROBE_BYTES, 'Empty or oversized decoded PTS output')
    values = []
    for line in proc.stdout.decode('utf-8').splitlines():
        cell = line.split(',', 1)[0].strip()
        if not cell or cell == 'N/A':
            continue
        try:
            number = float(cell)
        except ValueError as exc:
            raise ValueError('Invalid decoded frame PTS') from exc
        require(math.isfinite(number) and -0.05 <= number <= 4000,
                'Out-of-range decoded frame PTS')
        values.append(number)
        require(len(values) <= MAX_FRAMES, 'Too many decoded frame timestamps')
    require(bool(values), 'No usable decoded frame PTS')
    return sorted(values)


def _spacing(values):
    unique = sorted(set(values))
    gaps = [b - a for a, b in zip(unique, unique[1:])]
    return {
        'decoded_frame_count': len(values),
        'unique_pts_count': len(unique),
        'duplicate_pts_count': len(values) - len(unique),
        'first_observed_pts_seconds': unique[0],
        'last_observed_pts_seconds': unique[-1],
        'median_positive_gap_seconds': statistics.median(gaps) if gaps else None,
        'max_positive_gap_seconds': max(gaps) if gaps else None,
        'variable_spacing_observed_in_sample': bool(gaps) and max(gaps) - min(gaps) > 0.001,
    }


def _nearest(values, expected):
    idx = bisect_left(values, expected)
    choices = values[max(0, idx-1):min(len(values), idx+1)]
    require(bool(choices), 'No source frame candidates')
    return min(choices, key=lambda value: (abs(value - expected), value))


def _export_video_start_pts(path):
    """Read clip stream origin; retain nonzero origin instead of hiding it."""
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
           '-show_entries', 'stream=start_time', '-of', 'json', str(path)]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        raise ValueError(f'Clip stream origin probe failed: {type(exc).__name__}') from exc
    require(len(proc.stdout) < 8192, 'Oversized clip origin metadata')
    try:
        streams = json.loads(proc.stdout)['streams']
        require(type(streams) is list and len(streams) == 1,
                'Ambiguous clip video PTS origin')
        origin = float(streams[0]['start_time'])
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise ValueError('Unknown clip video PTS origin') from exc
    require(math.isfinite(origin) and -0.05 <= origin <= 0.5,
            'Clip video PTS origin outside supported window')
    return origin


def _validate_sidecar(sidecar, source_sha, clip_sha):
    require(type(sidecar) is dict and type(sidecar.get('schema_version')) is int and
            sidecar['schema_version'] == 1 and
            sidecar.get('status') == 'manual_clip_not_video_hand_verified',
            'Expected Cycle 109 manual clip sidecar')
    require(all(sidecar.get(key) is False for key in SIDECAR_FALSE_FLAGS),
            'Sidecar falsely claims verification')
    selection = validate_selection(sidecar.get('selection'))
    require(sidecar.get('source_sha256') == source_sha and
            selection['recording_sha256'] == source_sha and
            sidecar.get('output_sha256') == clip_sha,
            'Source or clip SHA-256 mismatch')
    require(_finite(sidecar.get('output_duration_seconds')),
            'Invalid declared output duration')
    return selection


def build_report(source_path, clip_path, sidecar, *, source_sha, clip_sha,
                 tolerance_seconds=0.125):
    """Compare observed decoded PTS under a *nominal* manual trim offset."""
    require(_finite(tolerance_seconds) and 0.01 <= tolerance_seconds <= 0.5,
            'Invalid PTS proximity tolerance')
    selection = _validate_sidecar(sidecar, source_sha, clip_sha)
    source, clip = Path(source_path), Path(clip_path)
    source_meta, clip_meta = probe(source), probe(clip)
    source_video_start_pts(source)
    clip_origin = _export_video_start_pts(clip)
    start, end = selection['start_seconds'], selection['end_seconds']
    duration = end - start
    require(end <= source_meta['duration_seconds'] + 0.01 and
            abs(clip_meta['duration_seconds'] - duration) <= 0.35 and
            abs(sidecar['output_duration_seconds'] - clip_meta['duration_seconds']) <= 0.05,
            'Media and manual selection duration mismatch')
    crop = selection['crop']
    if crop:
        require(crop['x'] + crop['width'] <= source_meta['width'] and
                crop['y'] + crop['height'] <= source_meta['height'] and
                (clip_meta['width'], clip_meta['height']) == (crop['width'], crop['height']),
                'Crop geometry mismatch')
    else:
        require((clip_meta['width'], clip_meta['height']) ==
                (source_meta['width'], source_meta['height']), 'Clip geometry mismatch')

    # Guard band reduces (but cannot eliminate) seek/keyframe incompleteness.
    source_begin = max(0.0, start - 8.0)
    source_span = min(MAX_WINDOW_SECONDS,
                      min(source_meta['duration_seconds'] - source_begin + 0.5,
                          end - source_begin + 8.0))
    source_pts = decoded_pts(source, source_begin, source_span)
    clip_pts = decoded_pts(clip, 0.0, min(MAX_WINDOW_SECONDS,
                                         clip_meta['duration_seconds'] + 0.5))
    # Trim sampled source PTS to a small margin around the claimed selection.
    source_near = sorted(set(p for p in source_pts if start - 0.5 <= p <= end + 0.5))
    clip_near = sorted(set(p for p in clip_pts if -0.05 <= p <= duration + 0.35))
    require(bool(source_near) and bool(clip_near), 'No PTS near selected interval')
    n = min(MAX_SAMPLES, len(clip_near))
    indexes = sorted({round(i * (len(clip_near) - 1) / max(1, n - 1))
                      for i in range(n)})
    samples = []
    for index in indexes:
        clip_time = clip_near[index]
        nominal_source_time = start + (clip_time - clip_origin)
        nearest = _nearest(source_near, nominal_source_time)
        signed = nearest - nominal_source_time
        samples.append({
            'decoded_clip_pts_seconds': round(clip_time, 6),
            'nominal_source_pts_seconds': round(nominal_source_time, 6),
            'nearest_observed_source_pts_seconds': round(nearest, 6),
            'signed_proximity_seconds': round(signed, 6),
            'absolute_proximity_seconds': round(abs(signed), 6),
            'within_tolerance': abs(signed) <= tolerance_seconds,
        })
    offsets = [x['absolute_proximity_seconds'] for x in samples]
    return {
        'schema_version': 1,
        'status': 'sampled_decoded_pts_proximity_not_frame_identity_or_hand_verified',
        'source_sha256': source_sha, 'clip_sha256': clip_sha,
        'selection_sha256': hashlib.sha256(json.dumps(selection, sort_keys=True,
                           separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
        'table_id_human_selected': selection['table_id'],
        'manual_clip_window_seconds': [start, end],
        'clip_video_stream_start_pts_seconds': clip_origin,
        'nonzero_clip_video_stream_start_pts_observed': abs(clip_origin) > 0.05,
        'clip_video_stream_duration_seconds': clip_meta['duration_seconds'],
        'clip_video_duration_shortfall_seconds': round(max(0.0, duration - clip_meta['duration_seconds']), 6),
        'source_requested_probe_window_seconds': [source_begin, source_begin + source_span],
        'source_pts_observation': _spacing(source_pts),
        'clip_pts_observation': _spacing(clip_pts),
        'tolerance_seconds': tolerance_seconds,
        'samples': samples,
        'max_sampled_abs_proximity_seconds': max(offsets),
        'median_sampled_abs_proximity_seconds': statistics.median(offsets),
        'samples_within_tolerance': sum(x['within_tolerance'] for x in samples),
        'actual_decoded_frame_pts_measured': True,
        'frame_exact_export_verified': False,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'strategic_error_established': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Both sets of decoded frame PTS are observed, but no decoded frame pixels are matched.',
            'Nominal source timestamp is manual start plus (clip PTS minus clip stream start PTS).',
            'FFprobe read_intervals may seek to a keyframe and omit some frames.',
            'Transcoding can duplicate, drop, shift or interpolate frames, particularly with VFR.',
            'Small timestamp proximity is not proof of frame identity, OCR, hand boundaries or EV.',
            'A nonzero clip stream start PTS can expose encoder trim or timing gaps.',
            'The manual trim offset is assumed, not independently verified from video content.',
        ],
    }


def export_report(source_path, clip_path, sidecar_path, output_path,
                  tolerance_seconds=0.125):
    source, clip, sidecar, output = map(Path, (source_path, clip_path, sidecar_path, output_path))
    require(len({p.resolve() for p in (source, clip, sidecar, output)}) == 4,
            'Input/output paths overlap')
    require(all(p.is_file() and not p.is_symlink() and p.stat().st_size > 0
                for p in (source, clip, sidecar)) and
            sidecar.stat().st_size <= MAX_SIDECAR_BYTES and
            output.suffix.lower() == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists(),
            'Unsafe input/output paths')
    sidecar_bytes = sidecar.read_bytes()
    require(0 < len(sidecar_bytes) <= MAX_SIDECAR_BYTES, 'Unsafe sidecar size')
    data = read_selection(sidecar)
    source_sha, clip_sha = digest_file(source), digest_file(clip)
    result = build_report(source, clip, data, source_sha=source_sha,
                          clip_sha=clip_sha, tolerance_seconds=tolerance_seconds)
    require(sidecar.read_bytes() == sidecar_bytes and
            digest_file(source) == source_sha and digest_file(clip) == clip_sha,
            'Input changed during decoded PTS comparison')
    result['sidecar_sha256'] = hashlib.sha256(sidecar_bytes).hexdigest()
    payload = (json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    require(len(payload) <= MAX_REPORT_BYTES, 'Decoded PTS report too large')
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recorded_video')
    parser.add_argument('exported_clip_mp4')
    parser.add_argument('manual_clip_sidecar_json')
    parser.add_argument('new_pts_comparison_json')
    parser.add_argument('--tolerance', type=float, default=0.125)
    args = parser.parse_args(argv)
    report = export_report(args.recorded_video, args.exported_clip_mp4,
                           args.manual_clip_sidecar_json,
                           args.new_pts_comparison_json, args.tolerance)
    print(json.dumps({'status': report['status'],
                      'samples': len(report['samples']),
                      'max_sampled_abs_proximity_seconds': report['max_sampled_abs_proximity_seconds']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
