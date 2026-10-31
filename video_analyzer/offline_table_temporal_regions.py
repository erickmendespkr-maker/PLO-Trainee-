"""Unverified temporal table-region candidates from an offline recorded video.

Never authorizes crops, OCR, equity or EV. Timestamps indicate sampled evidence,
not the exact moment a window moved. Layout identity is NOT tracked through
rearrangements: topology changes and large shifts are explicitly ambiguous.

Usage: python offline_table_temporal_regions.py VIDEO EXISTING_OUTPUT_DIR --interval 10
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

import offline_table_region_proposals as base

STATUS = 'offline_table_temporal_regions_unverified'
METHOD = 'ffmpeg_gray_160x90_independent_neighbor_contrast_v1'


def sample_times(duration, interval, max_samples):
    base.require(type(interval) in (int, float) and math.isfinite(interval)
                 and 1 <= interval <= 300, 'invalid sampling interval')
    base.require(type(max_samples) is int and 2 <= max_samples <= 720,
                 'invalid sample limit')
    count = math.ceil(duration / interval)
    base.require(2 <= count <= max_samples, 'duration/interval exceeds sample budget')
    return [round(min(duration - 0.001, (i + 0.5) * interval), 6)
            for i in range(count)]


def boundaries(regions):
    """Candidate dividing lines; only meaningful if the topology is unchanged."""
    xs = sorted({r['x'] for r in regions if r['x'] > 0})
    ys = sorted({r['y'] for r in regions if r['y'] > 0})
    return xs, ys


def compare(previous, current, width, height):
    if len(previous) != len(current) or len(boundaries(previous)[0]) != len(boundaries(current)[0]) or len(boundaries(previous)[1]) != len(boundaries(current)[1]):
        return 'topology_change_ambiguous', None
    old_x, old_y = boundaries(previous)
    new_x, new_y = boundaries(current)
    dx = max((abs(a - b) for a, b in zip(old_x, new_x)), default=0)
    dy = max((abs(a - b) for a, b in zip(old_y, new_y)), default=0)
    if dx > width * .20 or dy > height * .20:
        return 'large_shift_ambiguous', {'max_dx_px': dx, 'max_dy_px': dy}
    if dx or dy:
        return 'region_shift_candidate', {'max_dx_px': dx, 'max_dy_px': dy}
    return 'no_detected_shift', {'max_dx_px': 0, 'max_dy_px': 0}


def analyze_frames(frames, times, width, height):
    base.require(len(frames) == len(times) and len(times) >= 2, 'invalid frame series')
    observations, transitions = [], []
    last_good = None
    last_time = None
    for frame, timestamp in zip(frames, times):
        base.require(type(frame) is bytes and len(frame) == base.W * base.H,
                     'invalid grayscale frame')
        xaxis, yaxis = base.best_axis([frame], True), base.best_axis([frame], False)
        regions = base.propose_regions(width, height, xaxis, yaxis)
        # A featureless frame does not prove that one table fills the screen.
        supported = xaxis['supported_by_heuristic'] or yaxis['supported_by_heuristic']
        state = 'candidate_only' if supported else 'unsupported'
        event = None
        if last_good is not None:
            if not supported:
                state = 'ambiguous'
                event = ('heuristic_evidence_lost', None)
            else:
                event = compare(last_good, regions, width, height)
                if event[0].endswith('_ambiguous'):
                    state = 'ambiguous'
                elif event[0] == 'no_detected_shift':
                    event = None
        if event is not None:
            transitions.append({'first_observed_at_seconds': timestamp,
                                'possible_change_window_seconds': [last_time, timestamp],
                                'type': event[0], 'displacement': event[1],
                                'requires_human_review': True})
        observations.append({'timestamp_seconds': timestamp,
                             'status': state, 'regions': regions,
                             'vertical_seam_evidence': xaxis,
                             'horizontal_seam_evidence': yaxis})
        if supported and state == 'candidate_only':
            last_good = regions
        last_time = timestamp
    return observations, transitions


def track(video, output_dir, *, interval=10, max_samples=360):
    video, output_dir = Path(video), Path(output_dir)
    base.require(video.suffix.lower() in ('.mp4', '.webm', '.mov'), 'unsupported extension')
    base.safe_file(video)
    base.require(output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe output directory')
    base.require(output_dir.resolve() != video.parent.resolve(), 'separate output directory required')
    dest = output_dir / 'temporal_regions.json'
    base.require(not dest.exists() and not dest.is_symlink(), 'output collision')
    width, height, duration = base.probe(video)
    times = sample_times(duration, interval, max_samples)
    original_sha = base.sha256(video)
    frames = [base.sample(video, t) for t in times]
    observations, transitions = analyze_frames(frames, times, width, height)
    base.require(base.sha256(video) == original_sha, 'source changed during analysis')
    payload = {'schema_version': 1, 'status': STATUS, 'method': METHOD,
               'source_video_sha256': original_sha,
               'source_width': width, 'source_height': height,
               'source_duration_seconds': duration, 'sample_interval_seconds': interval,
               'observations': observations, 'transitions': transitions,
               'human_confirmation': False, 'crop_authorized': False,
               'automatic_ocr_math_authorization': False,
               'warning': 'Unverified sampled geometry. No table identity guarantee, no exact transition timestamp, no automatic crop/OCR/equity/EV authorization.'}
    with tempfile.TemporaryDirectory(prefix='plo_temporal_', dir=output_dir) as folder:
        temp = Path(folder) / dest.name
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        base.require(base.sha256(video) == original_sha, 'source changed before publishing')
        base.require(not dest.exists() and not dest.is_symlink(), 'output collision')
        os.link(temp, dest)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('output_dir')
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--max-samples', type=int, default=360)
    args = parser.parse_args(argv)
    result = track(args.video, args.output_dir, interval=args.interval,
                   max_samples=args.max_samples)
    print(json.dumps({'status': result['status'],
                      'observations': len(result['observations']),
                      'transitions': len(result['transitions'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
