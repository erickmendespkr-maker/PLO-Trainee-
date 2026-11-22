"""Conservative evidence gate for offline PLO video analysis.

Does not infer unseen cards or claim a GTO solution.
"""
import math

REQUIRED = ('table_id', 'hand_start_s', 'hand_end_s', 'hero_cards', 'board', 'action', 'pot', 'amount')


def assess_hand_evidence(hand, *, minimum_confidence=0.90):
    """Require human-reviewed fields before attaching conditional analysis."""
    if isinstance(minimum_confidence, bool) or not isinstance(minimum_confidence, (int, float)) or not math.isfinite(minimum_confidence) or not 0 <= minimum_confidence <= 1:
        raise ValueError('minimum_confidence must be in [0,1]')
    if not isinstance(hand, dict):
        raise ValueError('hand must be a mapping')
    missing, unverified, invalid = [], [], []
    for name in REQUIRED:
        item = hand.get(name)
        if not isinstance(item, dict) or item.get('value') is None:
            missing.append(name)
            continue
        value, confidence = item['value'], item.get('confidence')
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            invalid.append(name)
            continue
        if item.get('human_verified') is not True or confidence < minimum_confidence:
            unverified.append(name)
        if name in ('hand_start_s', 'hand_end_s', 'pot', 'amount') and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            invalid.append(name)
    if not any(k in missing + invalid for k in ('hand_start_s', 'hand_end_s')):
        if hand['hand_end_s']['value'] <= hand['hand_start_s']['value']:
            invalid.append('hand_interval')
    status = 'EVIDENCE_REVIEWED' if not (missing or unverified or invalid) else 'INSUFFICIENT_DATA'
    return {'status': status, 'missing_fields': sorted(missing), 'unverified_fields': sorted(unverified), 'invalid_fields': sorted(set(invalid)), 'strategic_verification': False, 'ev_is_conditional': True}
