"""Join named hypothetical EV scenarios; never infer observed hands or GTO."""
import math
from .offline_ev_loss_bounds import ev_loss_bounds
from .offline_ev_uncertainty import compare_actions

def decision_report(scenarios, chosen_action, *, unit, assumptions, hand_reviewed=False):
    """Produce deterministic model bounds in a declared unit, without publication approval."""
    if unit not in ('bb', 'chips'):
        raise ValueError('unit must be bb or chips')
    if not isinstance(assumptions, dict) or not assumptions:
        raise ValueError('explicit model assumptions required')
    if any(not isinstance(k, str) or not k.strip()
           or not isinstance(v, (str, int, float, bool))
           or isinstance(v, float) and not math.isfinite(v)
           for k, v in assumptions.items()):
        raise ValueError('invalid assumptions')
    if type(hand_reviewed) is not bool:
        raise ValueError('hand_reviewed must be boolean')
    loss = ev_loss_bounds(scenarios, chosen_action)
    names = list(scenarios)
    actions = list(next(iter(scenarios.values())))
    by_action = {action: [scenarios[name][action] for name in names]
                 for action in actions}
    comparison = compare_actions(by_action)
    robust = comparison['robust_action']
    return {
        'status': 'CONDITIONAL_MODEL_ONLY' if robust else 'RANGE_SENSITIVE',
        'chosen_action': chosen_action,
        'robust_action': robust,
        'scenario_ids': names,
        'unit': unit,
        'assumptions': dict(assumptions),
        'ev_envelopes': comparison['ev_envelopes'],
        'ev_loss': loss,
        'reviewed_hand_claimed_by_caller': hand_reviewed,
        'visual_hand_verified_by_this_module': False,
        'gto_solution': False,
        'interval_type': 'hypothetical_model_bounds_not_statistical_confidence',
        'publication_requires_external_review_binding': True,
    }
