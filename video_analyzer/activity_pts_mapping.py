"""Conservative mapping of offline requested seeks to decoded FFmpeg source PTS.

A mapping is evidence of a decoded frame, NOT a verified capture time,
poker action, hand boundary, or correct OCR result.
"""
from bisect import bisect_left
import math


def resolve_requested_pts(requested_times, decoded_pts, *, max_drift_seconds=2.):
    """Return (resolved, unresolved), preserving each requested seek.

    decoded_pts is a sequence of (integer PTS ticks, finite seconds), already
    parsed from FFmpeg showinfo. Multiple requests may map to the same frame.
    Missing or distant frames remain unresolved; no timestamps are fabricated.
    """
    if (type(max_drift_seconds) not in (int, float)
            or not math.isfinite(max_drift_seconds)
            or not 0 < max_drift_seconds <= 30):
        raise ValueError('Invalid maximum seek drift')
    if (not isinstance(requested_times, (list, tuple))
            or not isinstance(decoded_pts, (list, tuple))
            or len(requested_times) > 600 or len(decoded_pts) > 600):
        raise ValueError('Invalid seek or decoded PTS sequence')
    previous = -1.
    for t in requested_times:
        if type(t) not in (int, float) or not math.isfinite(t) or t < 0 or t <= previous:
            raise ValueError('Requested seeks must be finite, ordered and unique')
        previous = t
    times, last = [], -1.
    for pair in decoded_pts:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('Invalid decoded PTS row')
        ticks, seconds = pair
        if (type(ticks) is not int or ticks < 0 or type(seconds) not in (int, float)
                or not math.isfinite(seconds) or seconds < 0 or seconds <= last):
            raise ValueError('Decoded PTS must be finite and strictly increasing')
        times.append(float(seconds))
        last = seconds
    resolved, unresolved = [], []
    for seek in requested_times:
        index = bisect_left(times, seek - 1e-6)
        if index >= len(times) or times[index] - seek > max_drift_seconds:
            unresolved.append({'requested_seek_seconds': seek,
                               'reason': 'no_decoded_frame_within_seek_drift'})
        else:
            resolved.append({'requested_seek_seconds': seek, 'frame_index': index,
                             'source_pts_ticks': decoded_pts[index][0],
                             'timestamp_seconds': times[index],
                             'seek_drift_seconds': round(times[index] - seek, 8)})
    return resolved, unresolved
