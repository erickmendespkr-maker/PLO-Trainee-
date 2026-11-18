"""Conservative heads-up call EV sensitivity; not a GTO solver.

Equity intervals are externally supplied and must be independently validated.
No multiway pots, side pots, or future betting are modeled.
"""
from math import isfinite

def call_ev_envelope(pot_before_call, call_cost, scenarios, *, rake=0.0):
    """Incremental call EV versus fold=0, under explicit hypothetical ranges.

    Pot includes the opponent's outstanding bet, but not hero's call.
    Fixed rake is charged on wins only (simplified model).
    """
    values = (pot_before_call, call_cost, rake)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in values):
        raise ValueError("invalid monetary input")
    p, c, r = map(float, values)
    if p < 0 or c <= 0 or r < 0 or r > p:
        raise ValueError("invalid pot, call cost or rake")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("at least one scenario required")
    results = []
    seen = set()
    for s in scenarios:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not s["name"].strip() or s["name"] in seen:
            raise ValueError("scenario name invalid or duplicated")
        seen.add(s["name"])
        lo, hi = s.get("equity_low"), s.get("equity_high")
        if any(isinstance(q, bool) or not isinstance(q, (int, float)) or not isfinite(q) for q in (lo, hi)):
            raise ValueError("equity bounds must be finite numbers")
        if not 0 <= lo <= hi <= 1:
            raise ValueError("invalid equity interval")
        ev_lo = float(lo) * (p-r+c) - c
        ev_hi = float(hi) * (p-r+c) - c
        results.append({"name": s["name"], "ev_low": ev_lo, "ev_high": ev_hi,
                        "equity_low": float(lo), "equity_high": float(hi)})
    low = min(x["ev_low"] for x in results)
    high = max(x["ev_high"] for x in results)
    interpretation = ("call_positive_all_scenarios" if low > 0 else
                      "fold_positive_all_scenarios" if high < 0 else
                      "range_sensitive_or_uncertain")
    return {"status": "HYPOTHETICAL_ONLY", "pot_before_call": p, "call_cost": c,
            "fixed_win_rake": r, "ev_low": low, "ev_high": high,
            "scenario_results": results, "interpretation": interpretation,
            "fold_ev": 0.0, "units": "same_as_input",
            "assumptions": ["heads_up", "no_future_betting", "no_side_pots",
                            "fixed_rake_on_win_only", "equity_includes_tie_shares"],
            "gto_claim_permitted": False, "automatic_blunder_label_permitted": False}
