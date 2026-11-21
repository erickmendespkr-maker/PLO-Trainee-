"""Conservative offline join of Poker Cortes candidates and OCR stack samples.

The output is review-only. It cannot authorize loss labels, MP4 exports or EV.
"""
import math


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite numeric')
    if value < 0:
        raise ValueError(f'{name} must be nonnegative')
    return float(value)


def join_financial_evidence(candidate, samples, *, tolerance_seconds=1.0):
    """Attach independent OCR samples to an imported, unverified hand candidate.

    Each sample must have time_seconds, stack_bb, source_frame. A sample outside
    the hand interval is rejected, rather than silently associated to a hand.
    """
    if not isinstance(candidate, dict) or not isinstance(samples, list):
        raise ValueError('candidate must be object and samples must be list')
    start = _finite(candidate.get('start_seconds'), 'start_seconds')
    end = _finite(candidate.get('end_seconds'), 'end_seconds')
    tolerance = _finite(tolerance_seconds, 'tolerance_seconds')
    if end <= start:
        raise ValueError('hand interval must have positive duration')
    normalized = []
    seen = set()
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError('sample must be object')
        t = _finite(sample.get('time_seconds'), 'time_seconds')
        stack = _finite(sample.get('stack_bb'), 'stack_bb')
        frame = sample.get('source_frame')
        if not isinstance(frame, str) or not frame.strip():
            raise ValueError('source_frame required')
        if t < start - tolerance or t > end + tolerance:
            raise ValueError('sample outside hand interval')
        if t in seen:
            raise ValueError('duplicate sample timestamp')
        seen.add(t)
        normalized.append({'time_seconds': t, 'stack_bb': stack, 'source_frame': frame})
    normalized.sort(key=lambda item: item['time_seconds'])
    flags = ['FINANCIAL_RESULT_UNVERIFIED', 'HUMAN_REVIEW_REQUIRED']
    if len(normalized) < 2:
        flags.append('INSUFFICIENT_STACK_SAMPLES')
    else:
        for left, right in zip(normalized, normalized[1:]):
            if abs(right['stack_bb'] - left['stack_bb']) > 200:
                flags.append('LARGE_STACK_JUMP_RECHECK_OCR')
                break
    if candidate.get('source_rebuy_seen', candidate.get('rebuy_visto')) in (True, 'SIM', 'sim', 'YES', 'YES ', 'Sim'):
        flags.append('REBUY_REQUIRES_RECONCILIATION')
    return {
        'source': 'poker_cortes_turbo33',
        'candidate': candidate,
        'stack_samples': normalized,
        'flags': sorted(set(flags)),
        'confirmed_loss_bb': None,
        'clip_loss_label_authorized': False,
        'strategy_analysis_authorized': False,
        'verified_by_human': False,
    }
