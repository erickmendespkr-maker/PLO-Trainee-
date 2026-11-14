"""Conservative offline heads-up call EV. Hypothetical inputs; not GTO."""
import math

def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid " + label)
    return float(value)

def call_ev_bounds(*, pot_before_call, call_cost, equity_interval, rake_fraction=0, rake_cap=0):
    """Net incremental call EV vs fold=0; no future betting or side pots.

    Equity is a fractional share of the showdown pot, including ties.
    Rake is modeled only when a positive cap is explicitly provided.
    """
    p = _finite(pot_before_call, "pot")
    c = _finite(call_cost, "cost")
    r = _finite(rake_fraction, "rake fraction")
    cap = _finite(rake_cap, "rake cap")
    if c <= 0 or r > 1:
        raise ValueError("invalid call cost or rake fraction")
    if not isinstance(equity_interval, (list, tuple)) or len(equity_interval) != 2:
        raise ValueError("two equity endpoints required")
    lo, hi = [_finite(v, "equity") for v in equity_interval]
    if lo > hi or hi > 1:
        raise ValueError("equity outside [0,1]")
    gross = p + c
    rake = min(gross * r, cap) if cap > 0 else 0.0
    distributable = gross - rake
    return {
        "status": "HYPOTHETICAL_HEADS_UP_CALL_ONLY",
        "fold_ev": 0.0,
        "call_ev_interval": [lo * distributable - c, hi * distributable - c],
        "break_even_equity": c / distributable if distributable else None,
        "gross_pot": gross, "rake": rake,
        "assumptions": {"pot_before_call": p, "call_cost": c,
                        "equity_interval": [lo, hi], "rake_fraction": r,
                        "rake_cap": cap, "future_bets": False,
                        "side_pots": False, "opponents": 1},
        "equity_source": "USER_SUPPLIED_HYPOTHESIS",
        "ranges_verified": False, "gto_solution": False,
        "hand_error_verified": False,
    }
