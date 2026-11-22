"""Offline, fail-closed MP4 clip export with decoded-duration audit.

This module does not validate poker actions, cards or mathematical conclusions.
"""
import json
import math
import subprocess
from pathlib import Path


def export_review_clip(source, destination, *, start_s, end_s, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    values = (start_s, end_s)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
        raise ValueError('clip bounds must be finite numbers')
    if not 0 <= start_s < end_s:
        raise ValueError('invalid clip interval')
    source, destination = Path(source), Path(destination)
    if not source.is_file() or source.resolve() == destination.resolve():
        raise ValueError('source missing or destination equals source')
    if destination.suffix.lower() != '.mp4':
        raise ValueError('destination must be MP4')
    if destination.exists():
        raise FileExistsError('destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + '.partial.mp4')
    if temp.exists():
        raise FileExistsError('partial output already exists')
    try:
        probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(source)], capture_output=True, text=True, check=True)
        duration = float(json.loads(probe.stdout)['format']['duration'])
        if not math.isfinite(duration) or end_s > duration + 0.001:
            raise ValueError('clip exceeds source duration')
        subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start_s), '-i', str(source), '-t', str(end_s-start_s), '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(temp)], capture_output=True, text=True, check=True)
        result = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(temp)], capture_output=True, text=True, check=True)
        actual = float(json.loads(result.stdout)['format']['duration'])
        if not math.isfinite(actual) or abs(actual - (end_s-start_s)) > 0.25:
            raise ValueError('exported duration outside 250ms tolerance')
        # Fail closed if another process created the destination while encoding.
        # An exclusive hard link publishes the complete MP4 without overwriting it.
        import os
        os.link(temp, destination)
        return {'status': 'EXPORTED_TEMPORAL_ONLY', 'path': str(destination), 'requested_start_s': start_s, 'requested_end_s': end_s, 'actual_duration_s': actual, 'visually_verified': False}
    finally:
        if temp.exists():
            temp.unlink()
