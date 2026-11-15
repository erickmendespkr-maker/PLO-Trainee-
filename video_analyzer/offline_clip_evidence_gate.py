"""Conservative offline review gate for MP4 handoffs; never infers hidden cards."""
import math

REQUIRED = ('table_verified', 'hand_verified', 'hero_cards_verified',
            'board_verified', 'action_verified', 'amounts_verified')


def classify_clip_evidence(record):
    """Return a machine-readable approval status, not a poker recommendation.

    Missing/unknown fields always fail closed. Even APPROVED_CONDITIONAL
    requires explicit human review and scenario assumptions.
    """
    if not isinstance(record, dict):
        raise ValueError('record must be a dict')
    start, end = record.get('start_pts'), record.get('end_pts')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)):
        raise ValueError('finite numeric timestamps required')
    if start < 0 or end <= start:
        raise ValueError('invalid clip interval')
    if type(record.get('table_id')) is not int or not 1 <= record['table_id'] <= 4:
        raise ValueError('table_id must be 1..4')
    missing = [key for key in REQUIRED if record.get(key) is not True]
    if missing:
        return {'status': 'REVIEW_REQUIRED', 'missing_evidence': missing,
                'can_label_error': False, 'can_attach_conditional_ev': False,
                'start_pts': start, 'end_pts': end, 'table_id': record['table_id']}
    assumptions = record.get('ev_assumptions')
    missing_model = []
    if not isinstance(assumptions, dict):
        missing_model = ['ranges', 'rake', 'future_actions']
    else:
        for key in ('ranges', 'rake', 'future_actions'):
            value = assumptions.get(key)
            if key == 'rake':
                # Zero rake is an explicit valid scenario; bool and nonfinite are not.
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
            else:
                # Explicit strings such as 'none' for future actions are valid.
                valid = isinstance(value, (str, list, dict)) and bool(value)
            if not valid:
                missing_model.append(key)
    if missing_model:
        return {'status': 'INSUFFICIENT_MODEL',
                'missing_evidence': ['ev_assumptions.' + k for k in missing_model],
                'can_label_error': False, 'can_attach_conditional_ev': False,
                'start_pts': start, 'end_pts': end, 'table_id': record['table_id']}
    return {'status': 'APPROVED_CONDITIONAL', 'missing_evidence': [],
            'can_label_error': False, 'can_attach_conditional_ev': True,
            'start_pts': start, 'end_pts': end, 'table_id': record['table_id']}
