"""Conservative comparison of conditional EV scenario intervals; not GTO.

Each interval is a model-specific range (not a statistical confidence interval).
Never rank an action if intervals overlap or input is incomplete.
"""
import math


def compare_actions(scenarios):
    """Return a robust winner only if its worst EV exceeds every rival's best EV.

    scenarios maps action -> iterable of (low_ev, high_ev) bounds across
    explicit hypothetical ranges. All actions must share the same scenario count.
    """
    if not isinstance(scenarios, dict) or len(scenarios) < 2:
        raise ValueError('at least two actions required')
    bounds = {}
    count = None
    for action, intervals in scenarios.items():
        if action not in ('fold', 'call', 'raise') or not isinstance(intervals, (list, tuple)) or not intervals:
            raise ValueError('invalid action or missing scenarios')
        if count is None:
            count = len(intervals)
        if len(intervals) != count:
            raise ValueError('scenario count mismatch')
        for interval in intervals:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                raise ValueError('invalid interval')
            lo, hi = interval
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in (lo, hi)) or lo > hi:
                raise ValueError('invalid EV bounds')
        bounds[action] = (min(v[0] for v in intervals), max(v[1] for v in intervals))
    winners = [action for action, (lo, _) in bounds.items()
               if all(lo > hi for other, (_, hi) in bounds.items() if other != action)]
    return {'status': 'CONDITIONAL_MODEL_ONLY' if winners else 'RANGE_SENSITIVE',
            'robust_action': winners[0] if winners else None,
            'scenario_count': count, 'ev_envelopes': bounds,
            'gto_solution': False, 'visual_hand_verified': False}
