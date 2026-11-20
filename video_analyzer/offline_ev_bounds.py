"""Offline heads-up call EV sensitivity; conditional scenarios, never GTO advice."""
import math

def call_ev_bounds(pot_before_call, call_cost, equity_scenarios, rake=0.0):
    """Equity is expected pot share (ties included); rake is fixed on called pot.

    Net call EV = q*(pot_before_call + call_cost - rake) - call_cost.
    Fold EV is zero at decision point. No future betting or side pots.
    """
    values = (pot_before_call, call_cost, rake)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('nonfinite or nonnumeric money')
    p, c, r = map(float, values)
    if p < 0 or c <= 0 or r < 0 or r > p + c:
        raise ValueError('invalid pot, cost or rake')
    if not isinstance(equity_scenarios, dict) or not equity_scenarios:
        raise ValueError('named equity scenarios required')
    ev = {}
    for name, q in equity_scenarios.items():
        if not isinstance(name, str) or not name.strip() or name in ev:
            raise ValueError('invalid scenario name')
        if type(q) not in (float, int) or not math.isfinite(q) or not 0 <= q <= 1:
            raise ValueError('invalid equity')
        ev[name] = q * (p + c - r) - c
    low, high = min(ev.values()), max(ev.values())
    return {'model': 'heads_up_single_call_no_future_betting',
            'conditional_ev': ev, 'ev_min': low, 'ev_max': high,
            'decision_robust': 'call' if low > 0 else 'fold' if high < 0 else 'range_sensitive',
            'fold_ev': 0.0, 'units': 'same_as_input',
            'equity_source': 'user_supplied_scenarios_not_estimated',
            'gto_solution': False, 'strategic_verdict_allowed': False}
