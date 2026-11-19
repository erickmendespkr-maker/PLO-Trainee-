"""Conservative deterministic review queue for recorded-session hand proposals."""
import math

FIELDS = ('hero_cards', 'actions', 'pot', 'stacks', 'hand_boundaries')


def build_review_queue(proposals, *, limit=200):
    if not isinstance(proposals, list) or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('invalid proposals or limit')
    seen = set()
    queue = []
    for p in proposals:
        if not isinstance(p, dict):
            raise ValueError('invalid proposal')
        hand_id = p.get('hand_id')
        table_id = p.get('table_id')
        start, end = p.get('start_seconds'), p.get('end_seconds')
        invested = p.get('hero_invested_bb')
        if not isinstance(hand_id, str) or not 1 <= len(hand_id) <= 128 or hand_id in seen:
            raise ValueError('duplicate or invalid hand ID')
        seen.add(hand_id)
        if type(table_id) is not int or table_id not in (1, 2, 3, 4):
            raise ValueError('invalid table')
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in (start, end, invested)):
            raise ValueError('nonfinite timestamp or BB')
        if not 0 <= start < end or end - start > 600 or not 0 <= invested <= 100000:
            raise ValueError('invalid interval or BB')
        confidence = p.get('field_confidence')
        if not isinstance(confidence, dict) or set(confidence) != set(FIELDS):
            raise ValueError('all field confidences required')
        if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in confidence.values()):
            raise ValueError('invalid confidence')
        uncertain = [k for k in FIELDS if confidence[k] < 0.9]
        priority = (min(invested, 1000), len(uncertain), 1 - min(confidence.values()))
        queue.append({'hand_id': hand_id, 'table_id': table_id,
                      'start_seconds': start, 'end_seconds': end,
                      'hero_invested_bb': invested, 'uncertain_fields': uncertain,
                      'review_required': True, 'strategy_verified': False,
                      'is_gto': False, 'priority': priority})
    queue.sort(key=lambda x: (-x['priority'][0], -x['priority'][1], -x['priority'][2], x['start_seconds'], x['hand_id']))
    for item in queue:
        del item['priority']
    return {'schema_version': 1, 'ranking_basis': 'invested_bb_not_loss_or_ev',
            'analysis_verified': False, 'total_proposals': len(queue),
            'review_queue': queue[:limit]}
