"""Conservative temporal evidence checks for offline video crops.

A timestamp near a crop is not proof that the requested source interval exists.
"""
import math


def validate_source_interval(start, duration, source_duration, tolerance=0.25):
    """Reject invalid or out-of-bounds intervals; return inclusive bounds."""
    values = (start, duration, source_duration, tolerance)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('interval values must be finite numbers')
    if start < 0 or duration <= 0 or duration > 300 or source_duration <= 0:
        raise ValueError('invalid interval duration or start')
    if tolerance < 0 or tolerance > 2:
        raise ValueError('invalid tolerance')
    if start >= source_duration or start + duration > source_duration + tolerance:
        raise ValueError('interval outside source duration')
    return start, min(start + duration, source_duration)


def has_frame_inside_interval(frame_pts, start, duration, source_duration, tolerance=0.25):
    """Require a decoded PTS inside the requested interval, not merely nearby."""
    lower, upper = validate_source_interval(start, duration, source_duration, tolerance)
    for value in frame_pts:
        if type(value) not in (int, float) or not math.isfinite(value):
            continue
        if lower <= value <= upper:
            return True
    return False
