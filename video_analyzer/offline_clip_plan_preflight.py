"""Conservative validation for offline clip plans before FFmpeg writes outputs."""
import math
import re

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_HAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")

def validate_clip_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError('plan must be an object')
    if type(plan.get('table_id')) is not int or not 1 <= plan['table_id'] <= 4:
        raise ValueError('invalid table id')
    if type(plan.get('hand_id')) is not str or not _HAND.fullmatch(plan['hand_id']):
        raise ValueError('invalid hand id')
    if type(plan.get('source_sha256')) is not str or not _HASH.fullmatch(plan['source_sha256']):
        raise ValueError('invalid source hash')
    if plan.get('review_status') not in ('confirmed', 'insufficient_data'):
        raise ValueError('invalid review status')
    if plan.get('strategic_verdict_allowed') is not False:
        raise ValueError('strategic verdict forbidden')
    start, end, duration = (plan.get(k) for k in ('start_seconds', 'end_seconds', 'duration_seconds'))
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end, duration)):
        raise ValueError('invalid timestamps')
    if start < 0 or end <= start or abs(duration - (end - start)) > 1e-6:
        raise ValueError('invalid clip interval')
    return True
