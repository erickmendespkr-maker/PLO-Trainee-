"""Convert provisional handoff windows to explicitly unverified clip review records.

Never treats visual proposals as confirmed hands or strategy conclusions.
"""
import math


class ReviewRecordError(ValueError):
    pass


def review_records_from_handoff(handoff):
    """Return gate-compatible records, never approval for hand-specific EV."""
    if not isinstance(handoff, dict) or handoff.get('type') != 'provisional_clip_export_handoff' or handoff.get('schema_version') != 1:
        raise ReviewRecordError('invalid handoff schema')
    if handoff.get('human_review_required') is not True or handoff.get('gto_solution') is not False:
        raise ReviewRecordError('handoff safety flags invalid')
    duration = handoff.get('source_duration_seconds')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ReviewRecordError('invalid source duration')
    windows = handoff.get('windows')
    if not isinstance(windows, list):
        raise ReviewRecordError('windows must be a list')
    result = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            raise ReviewRecordError(f'invalid window {index}')
        table, start, end = window.get('table_id'), window.get('start_pts'), window.get('end_pts')
        if type(table) is not int or not 1 <= table <= 4:
            raise ReviewRecordError(f'invalid table {index}')
        if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= duration + 1e-6:
            raise ReviewRecordError(f'invalid interval {index}')
        ids = window.get('candidate_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(v, str) or not v.strip() for v in ids) or len(ids) != len(set(ids)):
            raise ReviewRecordError(f'invalid candidate ids {index}')
        if (window.get('hand_boundary_verified') is not False or
                window.get('human_review_required') is not True or
                window.get('export_approved') is not False or
                window.get('gto_solution') is not False or
                window.get('strategic_conclusion') is not None):
            raise ReviewRecordError(f'unsafe provisional flags {index}')
        result.append({'table_id': table, 'start_pts': start, 'end_pts': end,
                       'table_verified': False, 'hand_verified': False,
                       'hero_cards_verified': False, 'board_verified': False,
                       'action_verified': False, 'amounts_verified': False,
                       'candidate_ids': list(ids), 'human_review_required': True})
    return result
