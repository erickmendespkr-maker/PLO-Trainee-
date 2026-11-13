"""Compare decoded frame timelines, without asserting visual equivalence or hand identity."""
import math


def compare_frame_timelines(source_pts, clip_pts, start_seconds, end_seconds,
                            *, tolerance_seconds=0.06):
    """Check clip frame times against source frames in a declared interval.

    Input PTS arrays must come from independently decoded FFprobe observations.
    This is timing evidence only, never content verification.
    """
    for value in (start_seconds, end_seconds, tolerance_seconds):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('finite numeric bounds required')
    if start_seconds < 0 or end_seconds <= start_seconds or not 0 <= tolerance_seconds <= 0.25:
        raise ValueError('invalid interval or tolerance')

    def validate(values, label):
        if not isinstance(values, (list, tuple)) or not values or len(values) > 200000:
            raise ValueError(label + ' frame count invalid')
        previous = None
        for v in values:
            if type(v) not in (int, float) or not math.isfinite(v) or v < -0.001:
                raise ValueError(label + ' PTS invalid')
            if previous is not None and v <= previous:
                raise ValueError(label + ' PTS not increasing')
            previous = v
        return values

    source = validate(source_pts, 'source')
    clip = validate(clip_pts, 'clip')
    if clip[0] < -0.001 or clip[-1] - clip[0] > end_seconds - start_seconds + tolerance_seconds:
        raise ValueError('clip timeline outside requested duration')
    # Two-pointer nearest-frame check, O(source frames + clip frames).
    idx = 0
    maximum = 0.0
    for timestamp in clip:
        target = start_seconds + timestamp - clip[0]
        if target < start_seconds - tolerance_seconds or target > end_seconds + tolerance_seconds:
            raise ValueError('mapped frame outside source interval')
        while idx + 1 < len(source) and abs(source[idx + 1] - target) <= abs(source[idx] - target):
            idx += 1
        delta = abs(source[idx] - target)
        maximum = max(maximum, delta)
        if delta > tolerance_seconds:
            raise ValueError('source timeline has no matching frame')
    return {'status': 'FRAME_TIMING_CANDIDATE_ONLY',
            'source_frame_count': len(source), 'clip_frame_count': len(clip),
            'max_pts_delta_seconds': maximum, 'tolerance_seconds': tolerance_seconds,
            'source_timeline_verified': False, 'visual_hand_verified': False,
            'ev_verified': False, 'approved_for_publication': False,
            'limitations': ['timing_only', 'not_pixel_comparison', 'not_hand_identification']}
