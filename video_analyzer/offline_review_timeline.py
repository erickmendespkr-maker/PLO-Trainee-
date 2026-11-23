"""Conservative offline timeline checks for reviewed PLO hand ledgers.

Overlaps are warnings, not proof of incorrectly segmented hands. No OCR, equity,
EV, or gameplay is performed here.
"""
import math


def audit_review_timeline(history, *, max_tables=4, duration_s=None):
    if not isinstance(history, dict) or not isinstance(history.get('hands'), list):
        raise ValueError('history must contain a hands list')
    if not isinstance(max_tables, int) or isinstance(max_tables, bool) or not 1 <= max_tables <= 4:
        raise ValueError('max_tables must be an integer from 1 to 4')
    if duration_s is not None and (isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) or not math.isfinite(duration_s) or duration_s <= 0):
        raise ValueError('duration_s must be positive and finite')
    issues = []
    valid = {}
    for pos, hand in enumerate(history['hands']):
        if not isinstance(hand, dict):
            issues.append({'hand_index': pos, 'code': 'INVALID_HAND'}); continue
        table = hand.get('table_id')
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= max_tables:
            issues.append({'hand_index': pos, 'code': 'UNKNOWN_TABLE'}); continue
        start, end = hand.get('start_s'), hand.get('end_s')
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)) or start < 0 or end <= start:
            issues.append({'hand_index': pos, 'code': 'INVALID_INTERVAL'}); continue
        if duration_s is not None and end > duration_s:
            issues.append({'hand_index': pos, 'code': 'OUTSIDE_VIDEO'}); continue
        valid.setdefault(table, []).append((start, end, pos))
    for table, intervals in valid.items():
        intervals.sort()
        active_end, active_pos = -1, None
        for start, end, pos in intervals:
            if start < active_end:
                issues.append({'hand_index': pos, 'code': 'SAME_TABLE_OVERLAP', 'other_hand_index': active_pos, 'table_id': table})
            if end > active_end:
                active_end, active_pos = end, pos
    return {'status': 'REVIEW_REQUIRED' if issues else 'TIMELINE_PLAUSIBLE',
            'verified_hand_boundaries': False, 'issues': issues,
            'hands_checked': len(history['hands'])}
