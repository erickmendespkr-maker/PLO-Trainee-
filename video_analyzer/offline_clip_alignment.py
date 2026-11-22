"""Conservative timestamp alignment for offline hand clips.

A clip may cover a reviewed hand, but alignment does not verify its contents.
"""
import math
from collections.abc import Mapping


def audit_clip_alignment(analysis: Mapping, *, clip_start_s: float, clip_end_s: float,
                         video_duration_s: float, tolerance_s: float = 0.05) -> dict:
    """Check clip bounds and coverage of the reconstructed hand interval.

    Returns a status rather than guessing missing hand timestamps. A positive
    result is temporal only and must not be treated as visual verification.
    """
    values = (clip_start_s, clip_end_s, video_duration_s, tolerance_s)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('timestamps and tolerance must be finite numbers')
    if not (video_duration_s > 0 and tolerance_s >= 0 and
            0 <= clip_start_s < clip_end_s <= video_duration_s):
        raise ValueError('invalid clip or video interval')
    if not isinstance(analysis, Mapping):
        raise ValueError('analysis must be a mapping')
    start, end = analysis.get('start_s'), analysis.get('end_s')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
        return {'status': 'INSUFFICIENT_DATA', 'reason': 'HAND_TIMESTAMPS_MISSING', 'visually_verified': False}
    if not 0 <= start < end <= video_duration_s:
        return {'status': 'INSUFFICIENT_DATA', 'reason': 'HAND_INTERVAL_INVALID', 'visually_verified': False}
    if clip_start_s > start + tolerance_s or clip_end_s < end - tolerance_s:
        return {'status': 'INSUFFICIENT_DATA', 'reason': 'CLIP_DOES_NOT_COVER_HAND', 'visually_verified': False}
    return {'status': 'TEMPORALLY_ALIGNED_ONLY', 'reason': None,
            'hand_start_s': start, 'hand_end_s': end,
            'clip_start_s': clip_start_s, 'clip_end_s': clip_end_s,
            'visually_verified': False}
