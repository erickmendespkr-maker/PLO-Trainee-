"""Audit sparse video transition proposals without promoting them to hand facts."""
import math


def audit_transition_windows(windows, *, video_duration_seconds, max_tables=4):
    """Return an auditable summary and review queue; never infer hand boundaries."""
    if not isinstance(windows, list):
        raise ValueError('windows must be a list')
    if type(video_duration_seconds) not in (int, float) or not math.isfinite(video_duration_seconds) or video_duration_seconds <= 0:
        raise ValueError('invalid video duration')
    if type(max_tables) is not int or not 1 <= max_tables <= 4:
        raise ValueError('invalid max_tables')
    tables, queue = set(), []
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            raise ValueError('invalid window')
        table = window.get('table_id')
        start, end = window.get('earliest_pts'), window.get('latest_pts')
        if not isinstance(table, str) or not table.strip() or table != table.strip():
            raise ValueError('invalid table id')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
            raise ValueError('invalid timestamps')
        if not 0 <= start < end <= video_duration_seconds:
            raise ValueError('window outside video or zero width')
        if window.get('requires_review') is not True or window.get('usable_as_hand_boundary') is not False:
            raise ValueError('unverified window promoted to fact')
        if window.get('status') not in ('CANDIDATE', 'SPARSE_UNCERTAIN'):
            raise ValueError('invalid status')
        if window.get('gap_seconds') != end - start:
            raise ValueError('inconsistent gap')
        for field in ('start_frame_sha256', 'end_frame_sha256'):
            value = window.get(field)
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('invalid evidence hash')
        tables.add(table)
        queue.append({'source_index': index, 'table_id': table, 'earliest_pts': start,
                      'latest_pts': end, 'status': window['status'],
                      'review_required': True, 'hand_id': None})
    if len(tables) > max_tables:
        raise ValueError('too many tables')
    queue.sort(key=lambda item: (item['earliest_pts'], item['table_id'], item['latest_pts']))
    return {'status': 'REVIEW_REQUIRED', 'verified_hands': 0,
            'candidate_windows': len(queue), 'tables_observed': len(tables),
            'sparse_windows': sum(item['status'] == 'SPARSE_UNCERTAIN' for item in queue),
            'review_queue': queue}
