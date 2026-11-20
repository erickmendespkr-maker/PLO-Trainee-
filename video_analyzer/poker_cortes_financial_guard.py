"""Conservative offline guard for Poker Cortes stack OCR observations.

Stack changes alone never certify net hand profit/loss. All results require
independent financial reconciliation and human review before strategy or clips.
"""
import math


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be nonnegative' if not positive else f'{name} must be positive')
    return float(value)


def review_stack_samples(samples, *, max_jump_bb=200, tolerance_bb=0.5):
    """Review timestamped stack readings, never confirm loss or authorize EV.

    Each sample has time_seconds, stack_bb, source_frame and independent_read.
    independent_read is user-supplied metadata, not proof of independent OCR.
    """
    _number(max_jump_bb, 'max_jump_bb', positive=True)
    _number(tolerance_bb, 'tolerance_bb')
    if not isinstance(samples, list) or len(samples) < 2:
        raise ValueError('at least two stack samples required')
    seen = set()
    previous = None
    flags = set()
    normalized = []
    for item in samples:
        if not isinstance(item, dict):
            raise ValueError('sample must be an object')
        t = _number(item.get('time_seconds'), 'time_seconds')
        stack = _number(item.get('stack_bb'), 'stack_bb')
        frame = item.get('source_frame')
        if not isinstance(frame, str) or not frame.strip():
            raise ValueError('source_frame required')
        if previous is not None and t <= previous['time_seconds']:
            raise ValueError('timestamps must increase')
        if (t, frame) in seen:
            raise ValueError('duplicate observation')
        seen.add((t, frame))
        if previous is not None:
            change = stack - previous['stack_bb']
            if abs(change) > max_jump_bb:
                flags.add('LARGE_STACK_JUMP_RECHECK_OCR')
            if change > tolerance_bb:
                flags.add('STACK_INCREASE_CANNOT_ASSUME_POT_WIN')
            if change < -tolerance_bb:
                flags.add('STACK_DECREASE_CANNOT_ASSUME_NET_LOSS')
        normalized.append({'time_seconds': t, 'stack_bb': stack, 'source_frame': frame,
                           'independent_read': item.get('independent_read') is True})
        previous = normalized[-1]
    if not all(x['independent_read'] for x in normalized):
        flags.add('INDEPENDENT_VISUAL_READ_MISSING')
    return {'status': 'UNVERIFIED_REQUIRES_HUMAN_REVIEW',
            'confirmed_loss_bb': None, 'math_analysis_authorized': False,
            'clip_loss_label_authorized': False,
            'observed_stack_delta_bb': round(normalized[-1]['stack_bb'] - normalized[0]['stack_bb'], 6),
            'flags': sorted(flags), 'samples': normalized,
            'limitations': ['Stack delta is not net hand P/L',
                            'Rebuys, blinds, payouts, split pots and OCR require independent reconciliation']}
