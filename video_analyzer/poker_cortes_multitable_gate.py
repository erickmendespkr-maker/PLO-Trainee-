"""Offline multitable evidence router; proposals remain unverified.

Never associates an OCR sample with a hand from another table or video.
"""
import math
from collections import defaultdict

try:
    from .poker_cortes_evidence_gate import join_financial_evidence
except ImportError:
    from poker_cortes_evidence_gate import join_financial_evidence


def _time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid timestamp')
    return float(value)


def route_evidence(candidates, observations, *, max_tables=4):
    """Route samples only when a table/video/time matches exactly one candidate.

    Ambiguous observations are reported but not attached to either hand.
    """
    if not isinstance(candidates, list) or not isinstance(observations, list):
        raise ValueError('lists required')
    if isinstance(max_tables, bool) or not isinstance(max_tables, int) or not 1 <= max_tables <= 4:
        raise ValueError('max_tables must be 1..4')
    indexed = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError('candidate must be object')
        table = candidate.get('table_id')
        video = candidate.get('video_sha256')
        hand = candidate.get('hand_id')
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= max_tables:
            raise ValueError('invalid table')
        if not isinstance(video, str) or len(video) != 64 or any(c not in '0123456789abcdefABCDEF' for c in video):
            raise ValueError('invalid video hash')
        if not isinstance(hand, str) or not hand.strip():
            raise ValueError('invalid hand id')
        start, end = _time(candidate.get('start_seconds')), _time(candidate.get('end_seconds'))
        if end <= start:
            raise ValueError('invalid hand interval')
        key = (video.lower(), table, hand)
        if key in indexed:
            raise ValueError('duplicate hand')
        indexed[key] = candidate
    attached = defaultdict(list)
    unresolved = []
    for obs in observations:
        if not isinstance(obs, dict):
            raise ValueError('observation must be object')
        t = _time(obs.get('time_seconds'))
        table = obs.get('table_id')
        video = obs.get('video_sha256')
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= max_tables:
            raise ValueError('invalid observation table')
        if not isinstance(video, str) or len(video) != 64 or any(c not in '0123456789abcdefABCDEF' for c in video):
            raise ValueError('invalid observation video hash')
        # Validate evidence even when no hand matches; malformed OCR is not a benign miss.\n        stack = obs.get('stack_bb')\n        frame = obs.get('source_frame')\n        if isinstance(stack, bool) or not isinstance(stack, (int, float)) or not math.isfinite(stack) or stack < 0:\n            raise ValueError('invalid observation stack')\n        if not isinstance(frame, str) or not frame.strip():\n            raise ValueError('invalid observation frame')\n        matches = [key for key, hand in indexed.items()
                   if key[0] == video.lower() and key[1] == table and
                   hand['start_seconds'] <= t <= hand['end_seconds']]
        if len(matches) != 1:
            unresolved.append({'table_id': table, 'time_seconds': t,
                               'reason': 'AMBIGUOUS_HAND' if matches else 'NO_MATCHING_HAND'})
            continue
        attached[matches[0]].append({k: obs[k] for k in ('time_seconds', 'stack_bb', 'source_frame') if k in obs})
    results = []
    for key, hand in indexed.items():
        result = join_financial_evidence(hand, attached[key], tolerance_seconds=0)
        result['hand_key'] = {'video_sha256': key[0], 'table_id': key[1], 'hand_id': key[2]}
        results.append(result)
    return {'hands': results, 'unresolved_observations': unresolved,
            'financial_confirmation_authorized': False}
