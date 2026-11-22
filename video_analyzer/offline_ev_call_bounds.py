"""Auditable heads-up call EV bounds; not a GTO solver.

P is the pot before hero calls (including villain's outstanding bet).
C is hero's additional call cost. Equity is expected share including ties.
Assumes no rake, no side pots, no future betting and fixed conditional range.
"""
import math


def call_ev_bounds(*, pot_before: float, call_cost: float, equity_low: float, equity_high: float) -> dict:
    """Return net chip EV interval for a fixed range model, relative to folding.

    equity_low/high must be justified externally; this function does not
    estimate sampling confidence or uncertainty about the opponent range.
    """
    values = (pot_before, call_cost, equity_low, equity_high)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('all inputs must be finite numbers')
    if pot_before < 0 or call_cost <= 0 or pot_before < call_cost:
        raise ValueError('invalid pot or call cost')
    if not 0 <= equity_low <= equity_high <= 1:
        raise ValueError('invalid equity interval')
    # Net payoff on win = P; on loss = -C; fractional split is linear.
    low = equity_low * (pot_before + call_cost) - call_cost
    high = equity_high * (pot_before + call_cost) - call_cost
    return {
        'ev_low_chips': low,
        'ev_high_chips': high,
        'fold_ev_chips': 0.0,
        'break_even_equity': call_cost / (pot_before + call_cost),
        'range_sensitive': low <= 0 <= high,
        'assumptions': ['heads_up', 'fixed_conditional_range', 'no_rake', 'no_side_pots', 'no_future_betting'],
        'is_gto_solution': False,
    }
