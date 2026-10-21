"""Offline, unverified hints for new hands from repeated OCR card candidates."""
import math
from collections import defaultdict
from hand_history import validate_cards


def boundary_hints(stable_candidates, max_gap_seconds=90):
    """Suggest changes per table; never assign hand IDs or certify a boundary."""
    if not isinstance(stable_candidates, list) or len(stable_candidates) > 100000:
        raise ValueError('Invalid candidate list')
    if not isinstance(max_gap_seconds, (int, float)) or isinstance(max_gap_seconds, bool) or not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError('Invalid max gap')
    groups = defaultdict(list)
    for item in stable_candidates:
        if item.get('field') not in ('board', 'hero_cards'):
            continue
        table, field = item['table_id'], item['field']
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= 4:
            raise ValueError('Invalid table ID')
        if item.get('status') != 'temporally_repeated_unverified' or item.get('human_confirmed') is not False:
            raise ValueError('Expected unverified OCR candidate')
        start, end = item['first_timestamp'], item['last_timestamp']
        if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or x < 0 for x in (start, end)) or end < start:
            raise ValueError('Invalid timestamp')
        cards = item['parsed_candidate']
        validate_cards(cards)
        if len(cards) not in ((3, 4, 5) if field == 'board' else (5, 6)):
            raise ValueError('Invalid visible card count')
        groups[(table, field)].append((start, end, tuple(cards)))
    hints = []
    for (table, field), states in sorted(groups.items()):
        states.sort()
        for (a_start, a_end, a), (b_start, b_end, b) in zip(states, states[1:]):
            if b_start < a_end or b_start - a_end > max_gap_seconds:
                continue
            if field == 'hero_cards':
                changed = set(a) != set(b)
            else:
                changed = b != a and not (len(b) > len(a) and b[:len(a)] == a)
            if changed:
                hints.append({'table_id': table, 'field': field,
                              'timestamp': (a_end + b_start) / 2,
                              'reason': 'changed_private_cards' if field == 'hero_cards' else 'board_reset_or_conflict',
                              'status': 'needs_manual_review', 'human_confirmed': False})
    return {'schema_version': 1, 'analysis_status': 'unverified_boundary_hints_only',
            'boundary_hints': sorted(hints, key=lambda x: (x['timestamp'], x['table_id'])),
            'requires_manual_review': True}
