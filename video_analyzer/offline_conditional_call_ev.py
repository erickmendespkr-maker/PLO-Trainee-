"""Conservative conditional heads-up call EV, not a GTO solver.

P is the pot before calling, C is additional call cost, q is equity including ties.
Assumes no future betting, no rake, no side pots and a fixed opponent range.
"""
import math


def conditional_call_ev(pot_before_call, call_cost, equity, *, equity_ci=None):
    """Return incremental chip EV vs folding (fold = 0), with scenario assumptions.

    Equity uncertainty is sampling uncertainty only, not uncertainty in ranges.
    """
    values = (pot_before_call, call_cost, equity)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in values):
        raise ValueError("pot, cost and equity must be finite numbers")
    p, c, q = map(float, values)
    if p < 0 or c <= 0 or not 0 <= q <= 1:
        raise ValueError("invalid pot, cost or equity")
    if equity_ci is None:
        lo = hi = q
    else:
        if not isinstance(equity_ci, (tuple, list)) or len(equity_ci) != 2:
            raise ValueError("equity_ci must be a two-element interval")
        lo, hi = equity_ci
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) for v in (lo, hi)):
            raise ValueError("equity interval must be finite")
        if not 0 <= lo <= q <= hi <= 1:
            raise ValueError("equity interval must contain estimate and be within [0,1]")
    ev = lambda x: x * p - (1 - x) * c
    return {
        "method": "CONDITIONAL_HEADS_UP_CALL_NO_FUTURE_BETS",
        "fold_ev_chips": 0.0,
        "call_ev_chips": ev(q),
        "call_ev_interval_chips": [ev(lo), ev(hi)],
        "break_even_equity": c / (p + c),
        "range_uncertainty_included": False,
        "assumptions": [
            "heads_up", "fixed_opponent_range", "no_future_bets",
            "no_rake", "no_side_pots", "equity_includes_ties",
        ],
        "strategic_verdict": "NOT_ESTABLISHED",
    }
