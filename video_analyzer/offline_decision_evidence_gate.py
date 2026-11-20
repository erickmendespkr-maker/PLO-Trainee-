"""Independent conservative gate for attaching conditional EV to offline decisions."""
import hashlib
import json
import math
from offline_visible_card_contract import validate_fields

FIELDS = ('table_id', 'hand_id', 'start_seconds', 'end_seconds',
          'hero_cards', 'board_cards', 'action', 'pot', 'call_cost')

def evaluate(evidence, *, duration, video_sha256, audit=None):
    """Never equate a mathematical audit with a verified video observation."""
    if type(evidence) is not dict or type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid evidence/duration')
    if type(video_sha256) is not str or len(video_sha256) != 64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('invalid video digest')
    if audit is not None and type(audit) is not dict:
        raise ValueError('invalid audit')
    missing, unverified, values = [], [], {}
    for key in FIELDS:
        item = evidence.get(key)
        if type(item) is not dict or not {'value', 'confidence', 'human_verified'} <= item.keys():
            missing.append(key)
            continue
        conf = item['confidence']
        if type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1:
            raise ValueError('invalid confidence')
        if type(item['human_verified']) is not bool:
            raise ValueError('invalid review flag')
        values[key] = item['value']
        if not item['human_verified'] or item['value'] is None:
            unverified.append(key)
    if not missing:
        start, end = values['start_seconds'], values['end_seconds']
        if type(start) not in (int, float) or type(end) not in (int, float) or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration:
            raise ValueError('invalid timestamps')
        if type(values['table_id']) is not int or not 1 <= values['table_id'] <= 4:
            raise ValueError('invalid table')
        if type(values['hand_id']) is not str or not values['hand_id'].strip():
            raise ValueError('invalid hand ID')
    reviewed = not missing and not unverified
    if reviewed:
        validate_fields(values)
    audited = bool(audit and audit.get('ev_arithmetic_verified') is True
                   and type(audit.get('sample_hashes_verified')) is int
                   and audit['sample_hashes_verified'] > 0)
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 1, 'video_sha256': video_sha256,
            'evidence_sha256': digest, 'missing_fields': missing,
            'unverified_fields': unverified, 'clip_export_allowed': bool(reviewed),
            'conditional_analysis_attachment_allowed': bool(reviewed and audited),
            'strategic_verdict_allowed': False,
            'status': 'REVIEW_REQUIRED' if not reviewed else
                      'VISUAL_REVIEWED_CONDITIONAL_MODEL' if audited else
                      'VISUAL_REVIEWED_MATH_PENDING',
            'disclaimer': 'Conditional EV is not GTO or proof of a strategic mistake.'}
