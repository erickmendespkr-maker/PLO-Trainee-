"""Offline video table extraction: use manually specified or grid-based regions.

This is not a poker-table detector. Regions must be reviewed against the video.
"""
from pathlib import Path

from table_regions import validate_regions
from video_segments import _run


def crop_table_clip(source, output, region, frame_width, frame_height, start_seconds, end_seconds):
    """Crop one table and a time interval from a recording using FFmpeg."""
    validate_regions([region], frame_width, frame_height)
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Invalid clip timestamps")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    crop = f"crop={region.width}:{region.height}:{region.x}:{region.y}"
    _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
          '-ss', str(start_seconds), '-i', str(source),
          '-t', str(end_seconds - start_seconds), '-vf', crop,
          '-c:v', 'libx264', '-an', str(output)])
    return output
