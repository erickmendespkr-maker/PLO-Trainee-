"""Conservative decoded-frame PTS audit for exported offline MP4.

Does not establish correspondence to frames in the original recording.
"""
import json
import math
import subprocess
from pathlib import Path


def audit_decoded_pts(clip_path, ffprobe='ffprobe', max_frames=200000, timeout=90):
    path = Path(clip_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular non-symlink clip required')
    if type(max_frames) is not int or not 1 <= max_frames <= 200000:
        raise ValueError('invalid frame limit')
    try:
        proc = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                               '-show_frames', '-show_entries',
                               'frame=best_effort_timestamp_time', '-of', 'json', str(path)],
                              capture_output=True, text=True, timeout=timeout, check=True)
        frames = json.loads(proc.stdout)['frames']
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('ffprobe frame inspection failed') from exc
    if not isinstance(frames, list) or not frames or len(frames) > max_frames:
        raise ValueError('empty or excessive frame count')
    pts = []
    for frame in frames:
        if not isinstance(frame, dict) or 'best_effort_timestamp_time' not in frame:
            raise ValueError('missing decoded frame PTS')
        try:
            value = float(frame['best_effort_timestamp_time'])
        except (ValueError, TypeError) as exc:
            raise ValueError('invalid frame PTS') from exc
        if not math.isfinite(value) or value < -0.001:
            raise ValueError('nonfinite or negative PTS')
        if pts and value <= pts[-1]:
            raise ValueError('non-increasing decoded PTS')
        pts.append(value)
    return {'status': 'DECODED_PTS_MONOTONIC_ONLY', 'approved_for_publication': False,
            'frame_count': len(pts), 'first_pts_seconds': pts[0],
            'last_pts_seconds': pts[-1], 'source_timeline_verified': False,
            'visual_hand_verified': False, 'ev_verified': False}
