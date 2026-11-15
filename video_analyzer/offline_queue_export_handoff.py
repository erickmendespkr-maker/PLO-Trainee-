"""Conservative handoff from provisional review queue to clip export requests.

No provisional event is promoted to a verified hand or poker conclusion.
"""
import json
import math
from pathlib import Path

try:
    from .offline_decision_clip_queue import build_review_queue
except ImportError:
    from offline_decision_clip_queue import build_review_queue


class HandoffError(ValueError):
    pass


def build_export_handoff(records, *, source_duration, padding_seconds=2.0):
    """Return deterministic, non-overlapping review windows per table.

    Windows may overlap across different tables because they share a recording.
    These are proposals for manual review, not verified hand boundaries.
    """
    if type(source_duration) not in (int, float) or not math.isfinite(source_duration) or source_duration <= 0:
        raise HandoffError('invalid source duration')
    if type(padding_seconds) not in (int, float) or not math.isfinite(padding_seconds) or not 0 <= padding_seconds <= 30:
        raise HandoffError('invalid padding')
    queue = build_review_queue(records)
    windows = []
    for item in queue:
        if item['end_pts'] > source_duration + 1e-6:
            raise HandoffError('candidate exceeds recording duration')
        start = max(0.0, item['start_pts'] - padding_seconds)
        end = min(float(source_duration), item['end_pts'] + padding_seconds)
        windows.append((item['table_id'], start, end, item['candidate_id']))
    windows.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    grouped = []
    for table, start, end, candidate in windows:
        if grouped and grouped[-1]['table_id'] == table and start <= grouped[-1]['end_pts']:
            grouped[-1]['end_pts'] = max(grouped[-1]['end_pts'], end)
            grouped[-1]['candidate_ids'].append(candidate)
        else:
            grouped.append({'table_id': table, 'start_pts': start, 'end_pts': end,
                            'candidate_ids': [candidate]})
    for item in grouped:
        item['candidate_ids'].sort()
        item.update({'hand_boundary_verified': False, 'human_review_required': True,
                     'strategic_conclusion': None, 'ev_is_conditional': True,
                     'gto_solution': False, 'export_approved': False})
    return {'schema_version': 1, 'type': 'provisional_clip_export_handoff',
            'source_duration_seconds': float(source_duration), 'windows': grouped,
            'human_review_required': True, 'gto_solution': False}


def save_export_handoff(records, destination, *, source_duration, padding_seconds=2.0):
    result = build_export_handoff(records, source_duration=source_duration,
                                  padding_seconds=padding_seconds)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return result
