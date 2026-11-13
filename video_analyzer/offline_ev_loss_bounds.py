"""Conservative EV-loss bounds for explicitly named hypothetical range scenarios.

Model bounds are not statistical confidence intervals or GTO solutions.
"""
import math


def ev_loss_bounds(scenarios, chosen_action):
    """Return per-scenario possible regret relative to alternative actions."""
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError('named scenarios required')
    if chosen_action not in ('fold', 'call', 'raise'):
        raise ValueError('invalid chosen action')
    action_set = None
    losses = {}
    for scenario_id, actions in scenarios.items():
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError('invalid scenario identifier')
        if not isinstance(actions, dict) or len(actions) < 2 or chosen_action not in actions:
            raise ValueError('missing chosen action or alternatives')
        if any(a not in ('fold', 'call', 'raise') for a in actions):
            raise ValueError('invalid action')
        if action_set is None:
            action_set = frozenset(actions)
        elif frozenset(actions) != action_set:
            raise ValueError('scenario action mismatch')
        for bounds in actions.values():
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise ValueError('invalid bounds')
            lo, hi = bounds
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds) or lo > hi:
                raise ValueError('invalid EV bounds')
        own_low, own_high = actions[chosen_action]
        rivals = [bounds for action, bounds in actions.items() if action != chosen_action]
        lower = max(0.0, max(lo - own_high for lo, _ in rivals))
        upper = max(0.0, max(hi - own_low for _, hi in rivals))
        losses[scenario_id] = {'min_ev_loss': lower, 'max_ev_loss': upper}
    return {'chosen_action': chosen_action, 'per_scenario': losses,
            'overall_min_ev_loss': min(v['min_ev_loss'] for v in losses.values()),
            'overall_max_ev_loss': max(v['max_ev_loss'] for v in losses.values()),
            'status': 'CONDITIONAL_MODEL_ONLY', 'gto_solution': False,
            'visual_hand_verified': False,
            'interval_type': 'hypothetical_model_bounds_not_statistical_confidence'}
