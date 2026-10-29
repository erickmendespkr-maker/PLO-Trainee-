"""Offline, *visual-only* four-table change timeline for recorded PLO5/PLO6.

Example:
  python offline_four_table_visual_timeline.py session.mp4 NEW_TIMELINE.json --tables 4

Uses FFprobe and FFmpeg, samples frames without writing them to disk, retains
FFmpeg's sampled *source-frame* presentation timestamps, and computes independent
per-region pixel-change events. Changes are NOT proven hand boundaries, cards,
actions, OCR results, player identity, or poker decisions. No live capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

WIDTH, HEIGHT = 160, 96
FRAME_BYTES = WIDTH * HEIGHT
MAX_DURATION = 70 * 60
MAX_FRAMES = MAX_DURATION + 4
PTS_PATTERN = re.compile(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*([\d.eE+-]+)')


class TimelineError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise TimelineError(message)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect_video(path, ffprobe='ffprobe'):
    """Inspect a finite, bounded video; do not trust filename extensions alone."""
    path = Path(path).resolve(strict=True)
    require(path.is_file() and path.suffix.lower() in ('.mp4', '.webm', '.mkv'),
            'input must be an existing MP4/WebM/MKV')
    require(0 < path.stat().st_size <= 4 * 1024**3, 'invalid video file size')
    command = [ffprobe, '-v', 'error', '-select_streams', 'v:0',
               '-show_entries', 'stream=width,height,codec_type:format=duration',
               '-of', 'json', str(path)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    require(proc.returncode == 0, 'FFprobe could not inspect the video')
    try:
        info = json.loads(proc.stdout)
        stream = info['streams'][0]
        width, height = stream['width'], stream['height']
        duration = float(info['format']['duration'])
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise TimelineError('missing video dimensions or duration') from exc
    require(type(width) is int and type(height) is int and
            64 <= width <= 7680 and 64 <= height <= 4320,
            'unsupported video dimensions')
    require(math.isfinite(duration) and 0 < duration <= MAX_DURATION,
            'video duration outside supported range (up to 70 minutes)')
    return path, {'width': width, 'height': height, 'duration_seconds': duration}


def regions(tables):
    require(type(tables) is int and 1 <= tables <= 4, 'tables must be 1..4')
    if tables == 1:
        rects = [(0, 0, WIDTH, HEIGHT)]
    elif tables == 2:
        rects = [(0, 0, WIDTH // 2, HEIGHT), (WIDTH // 2, 0, WIDTH // 2, HEIGHT)]
    else:
        rects = [(0, 0, WIDTH // 2, HEIGHT // 2),
                 (WIDTH // 2, 0, WIDTH // 2, HEIGHT // 2),
                 (0, HEIGHT // 2, WIDTH // 2, HEIGHT // 2),
                 (WIDTH // 2, HEIGHT // 2, WIDTH // 2, HEIGHT // 2)][:tables]
    return [{'table_id': f'table_{i+1}', 'pixel_rect': list(rect),
             'normalized_rect': [x / WIDTH, y / HEIGHT, w / WIDTH, h / HEIGHT]}
            for i, rect in enumerate(rects) for x, y, w, h in [rect]]


def sampled_frames(path, *, ffmpeg='ffmpeg', interval=1.0, max_seconds=600):
    """Return (PTS, gray bytes) from selected source frames, not an invented clock.

    FFmpeg select retains input presentation timestamps; no setpts/fps rounding.
    The first selected frame and subsequent frames >= interval apart are used.
    Output is bounded by video duration and sample interval. No temp images.
    """
    require(type(interval) in (int, float) and math.isfinite(interval) and
            0.5 <= interval <= 5, 'sample interval must be 0.5..5 seconds')
    expression = f'isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval:.6f})'
    command = [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'info',
               '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn',
               '-vf', f'select={expression},scale={WIDTH}:{HEIGHT}:flags=area,format=gray,showinfo',
               '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1']
    proc = subprocess.run(command, capture_output=True, timeout=max_seconds, check=False)
    require(proc.returncode == 0, 'FFmpeg frame sampling failed')
    require(len(proc.stdout) % FRAME_BYTES == 0, 'truncated rawvideo output')
    n = len(proc.stdout) // FRAME_BYTES
    require(1 <= n <= int(MAX_DURATION / interval) + 4, 'unexpected frame count')
    logs = proc.stderr.decode('utf-8', errors='replace')
    pts = [(int(m.group(1)), float(m.group(3))) for m in PTS_PATTERN.finditer(logs)]
    require(len(pts) == n and all(i == k for k, (i, _) in enumerate(pts)),
            'sample frame/PTS mapping mismatch')
    timestamps = [p for _, p in pts]
    require(all(math.isfinite(t) and t >= 0 for t in timestamps) and
            all(a < b for a, b in zip(timestamps, timestamps[1:])),
            'invalid or nonmonotonic source timestamps')
    return [(t, memoryview(proc.stdout)[i * FRAME_BYTES:(i + 1) * FRAME_BYTES])
            for i, t in enumerate(timestamps)]


def change_fraction(previous, current, rect, *, pixel_delta=28):
    """Fraction of ROI pixels whose absolute grayscale difference exceeds delta."""
    x, y, w, h = rect
    require(len(previous) == len(current) == FRAME_BYTES, 'wrong frame dimensions')
    changed = 0
    for row in range(y, y + h):
        start = row * WIDTH + x
        changed += sum(abs(a - b) >= pixel_delta
                       for a, b in zip(previous[start:start+w], current[start:start+w]))
    return changed / (w * h)


def group_candidates(events, duration, *, padding=1.0, merge_gap=1.5):
    """Group candidate activity, never assert a hand start or end."""
    result = []
    for event in events:
        start, end = max(0., event['pts_seconds'] - padding), min(duration, event['pts_seconds'] + padding)
        if result and start - result[-1]['end_seconds'] <= merge_gap:
            result[-1]['end_seconds'] = max(result[-1]['end_seconds'], end)
            result[-1]['event_count'] += 1
            result[-1]['max_changed_fraction'] = max(result[-1]['max_changed_fraction'], event['changed_fraction'])
        else:
            result.append({'start_seconds': start, 'end_seconds': end,
                           'event_count': 1, 'max_changed_fraction': event['changed_fraction'],
                           'interpretation': 'visual_activity_only_not_verified_hand'})
    return result


def analyze(frames, metadata, tables=4, threshold=0.08):
    require(type(threshold) in (float, int) and math.isfinite(threshold) and
            0 < threshold <= 1, 'invalid change threshold')
    rois = regions(tables)
    require(frames and all(len(data) == FRAME_BYTES for _, data in frames), 'invalid frames')
    times = [t for t, _ in frames]
    require(all(math.isfinite(t) and t >= 0 for t in times) and
            all(a < b for a, b in zip(times, times[1:])), 'invalid frame timestamps')
    require(times[-1] <= metadata['duration_seconds'] + 0.5, 'sample beyond video duration')
    timeline = []
    for roi in rois:
        events = []
        for (t, current), (_, previous) in zip(frames[1:], frames[:-1]):
            fraction = change_fraction(previous, current, roi['pixel_rect'])
            if fraction >= threshold:
                events.append({'pts_seconds': round(t, 6),
                               'changed_fraction': round(fraction, 6)})
        timeline.append({**roi,
                         'source_pixel_rect': [round(roi['normalized_rect'][0] * metadata['width']),
                                               round(roi['normalized_rect'][1] * metadata['height']),
                                               round(roi['normalized_rect'][2] * metadata['width']),
                                               round(roi['normalized_rect'][3] * metadata['height'])],
                         'events': events,
                         'candidate_windows': group_candidates(events, metadata['duration_seconds'])})
    return {'schema_version': 1, 'analysis_status': 'synthetic_or_recorded_visual_change_proposals_only',
            'source_pts_kind': 'ffmpeg_selected_source_frame_presentation_timestamp',
            'sampled_frame_count': len(frames),
            'sample_pts_seconds': [round(t, 6) for t in times],
            'first_sample_pts_seconds': round(times[0], 6),
            'last_sample_pts_seconds': round(times[-1], 6),
            'change_threshold_fraction': threshold,
            'video': metadata, 'tables': timeline,
            'ocr_performed': False, 'hand_boundaries_verified': False,
            'actions_or_cards_identified': False,
            'manual_review_required': True,
            'limitations': ['Visual changes are not verified hand boundaries.',
                            'Static table positions are assumed; moving/resized tables need manual ROIs.',
                            'Source PTS reflect decoded selected frames, not every frame or wall-clock time.',
                            'Visual similarity cannot establish OCR, equity or EV.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('new_json')
    parser.add_argument('--tables', type=int, default=4)
    parser.add_argument('--interval', type=float, default=1.0)
    parser.add_argument('--threshold', type=float, default=0.08)
    args = parser.parse_args(argv)
    video, metadata = inspect_video(args.video)
    out = Path(args.new_json)
    require(out.suffix.lower() == '.json' and out.parent.is_dir() and
            not out.parent.is_symlink() and not out.exists() and not out.is_symlink() and
            out.resolve() != video, 'output must be a new JSON file')
    regions(args.tables)
    before = sha256_file(video)
    frames = sampled_frames(video, interval=args.interval)
    result = analyze(frames, metadata, args.tables, args.threshold)
    require(sha256_file(video) == before, 'video changed during analysis')
    result['video_sha256'] = before
    result['sample_interval_requested_seconds'] = args.interval
    with out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'tables': args.tables, 'frames': len(frames),
                      'candidate_windows': sum(len(t['candidate_windows']) for t in result['tables']),
                      'output': str(out), 'hands_verified': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
