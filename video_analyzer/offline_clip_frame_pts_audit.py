"""Bounded FFprobe frame-PTS sampling near *human-selected* offline clip edges.

The nearest observed decoded video-frame PTS is NOT a verified hand boundary,
a guaranteed global nearest frame, or a validation of human action timestamps.
Only local user-supplied recordings; never connects to live poker services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess

from offline_manual_clip_export import (digest_file, probe, read_selection,
                                        validate_selection, require)

MAX_OUTPUT = 1_048_576
WINDOW_SECONDS = 24.0


def frame_pts_near(source: Path, timestamp: float, duration: float):
    """Return observed frame PTS from a bounded *seek-dependent* sample.

    FFprobe seeks to a nearby keyframe; its read_intervals window is NOT an
    exhaustive proof of the globally nearest frame. The report says so.
    """
    begin = max(0.0, timestamp - 3.0)
    interval = min(WINDOW_SECONDS, duration - begin + 0.25)
    require(interval > 0, 'Empty probe interval')
    args = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-read_intervals', f'{begin:.6f}%+{interval:.6f}',
            '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time',
            '-of', 'csv=p=0', str(source)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=45, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'FFprobe frame sampling failed: {type(exc).__name__}') from exc
    require(len(proc.stdout) <= MAX_OUTPUT, 'Frame sample too large')
    pts = []
    for line in proc.stdout.decode('utf-8').splitlines():
        first = line.split(',', 1)[0].strip()
        if not first or first == 'N/A':
            continue
        try:
            value = float(first)
        except ValueError as exc:
            raise ValueError('Invalid decoded frame PTS') from exc
        require(math.isfinite(value) and -1 <= value <= duration + 5,
                'Out-of-bounds frame PTS')
        pts.append(value)
    require(bool(pts), 'No decoded video frame PTS in sampled interval')
    require(len(pts) <= 20000, 'Too many decoded frame timestamps')
    ordered = sorted(set(pts))
    nearest = min(ordered, key=lambda p: (round(abs(p - timestamp), 6), p))
    gaps = [b-a for a, b in zip(ordered, ordered[1:])]
    median = statistics.median(gaps) if gaps else None
    max_gap = max(gaps) if gaps else None
    return {
        'requested_seconds': timestamp,
        'nearest_observed_frame_pts_seconds': nearest,
        'signed_offset_seconds': round(nearest - timestamp, 6),
        'absolute_offset_seconds': round(abs(nearest - timestamp), 6),
        'sampled_frame_count': len(pts),
        'sampled_unique_pts_count': len(ordered),
        'duplicate_pts_count': len(pts)-len(ordered),
        'sampled_min_pts_seconds': ordered[0],
        'sampled_max_pts_seconds': ordered[-1],
        'median_sampled_frame_gap_seconds': median,
        'max_sampled_frame_gap_seconds': max_gap,
        'variable_spacing_observed': (bool(gaps) and max_gap - min(gaps) > 0.001),
        'requested_sampling_window_seconds': [begin, begin + interval],
        'sample_is_not_exhaustive_or_globally_nearest_proof': True,
    }


def source_video_start_pts(source):
    """Reject nonzero-origin sources until timeline normalization is supported."""
    args = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=start_time', '-of', 'json', str(source)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=20, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'FFprobe start PTS failed: {type(exc).__name__}') from exc
    require(len(proc.stdout) < 8192, 'Unexpected start PTS output')
    data = json.loads(proc.stdout)
    streams = data.get('streams', [])
    require(type(streams) is list and len(streams) == 1, 'Ambiguous video PTS origin')
    try:
        start = float(streams[0]['start_time'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Unknown video PTS origin') from exc
    require(math.isfinite(start) and abs(start) <= 0.05,
            'Nonzero video PTS origin requires explicit normalization')
    return start


def build_audit(source, selection, tolerance=0.25):
    source = Path(source)
    require(source.is_file() and not source.is_symlink(), 'Unsafe recording')
    require(type(tolerance) in (int, float) and math.isfinite(tolerance) and
            0.01 <= tolerance <= 1.0, 'Invalid tolerance')
    sel = validate_selection(selection)
    require(digest_file(source) == sel['recording_sha256'], 'Recording SHA-256 mismatch')
    meta = probe(source)
    origin = source_video_start_pts(source)
    require(sel['end_seconds'] <= meta['duration_seconds'] + 0.01,
            'Selection outside video timeline')
    crop = sel['crop']
    if crop is not None:
        require(crop['x'] + crop['width'] <= meta['width'] and
                crop['y'] + crop['height'] <= meta['height'], 'Crop outside source geometry')
    edges = {name: frame_pts_near(source, sel[name], meta['duration_seconds'])
             for name in ('start_seconds', 'end_seconds')}
    for row in edges.values():
        row['observed_frame_within_tolerance'] = row['absolute_offset_seconds'] <= tolerance
    require(digest_file(source) == sel['recording_sha256'],
            'Recording changed during frame audit')
    return {
        'schema_version': 1,
        'status': 'bounded_source_frame_pts_observation_not_hand_verified',
        'source_sha256': sel['recording_sha256'],
        'selection_sha256': hashlib.sha256(json.dumps(sel, sort_keys=True,
                                separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
        'table_id_human_selected': sel['table_id'],
        'container_duration_seconds': meta['duration_seconds'],
        'source_video_start_pts_seconds': origin,
        'tolerance_seconds': tolerance,
        'edges': edges,
        'both_edges_have_observed_frames_within_tolerance': all(
            e['observed_frame_within_tolerance'] for e in edges.values()),
        'source_frame_pts_observed': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'math_analysis_linked': False,
        'strategic_error_established': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Frame PTS proximity does not identify a poker hand or action boundary.',
            'FFprobe read_intervals seeks approximately and may miss the globally nearest frame.',
            'Nonzero-origin source PTS beyond 0.05 seconds are blocked pending normalization.',
            'Video frame PTS do not guarantee frame-accurate FFmpeg output trim.',
            'Frame spacing observations are local and cannot classify an entire recording as VFR.',
            'Human selected timestamps and OCR/ranges remain unverified.',
        ],
    }


def export_audit(source_path, selection_path, output_json, tolerance=0.25):
    source, selection, output = map(Path, (source_path, selection_path, output_json))
    require(len({p.resolve() for p in (source, selection, output)}) == 3,
            'Overlapping paths')
    require(output.suffix.lower() == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists(), 'Unsafe output path')
    sel = read_selection(selection)
    raw = selection.read_bytes()
    result = build_audit(source, sel, tolerance)
    require(selection.read_bytes() == raw, 'Selection changed during audit')
    payload = json.dumps(result, indent=2, ensure_ascii=False,
                         allow_nan=False).encode('utf-8') + b'\n'
    require(len(payload) <= MAX_OUTPUT, 'Audit output too large')
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
    parser.add_argument('human_clip_selection_json')
    parser.add_argument('new_frame_audit_json')
    parser.add_argument('--tolerance', type=float, default=0.25)
    args = parser.parse_args(argv)
    report = export_audit(args.recorded_video, args.human_clip_selection_json,
                          args.new_frame_audit_json, args.tolerance)
    print(json.dumps({'status': report['status'],
                      'edges_within_tolerance': report['both_edges_have_observed_frames_within_tolerance']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())