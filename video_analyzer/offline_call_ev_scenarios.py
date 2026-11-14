"""Offline conditional call EV across user-supplied equity scenarios; not GTO."""
from .offline_call_ev_bounds import call_ev_bounds

def evaluate_call_scenarios(*, pot_before_call, call_cost, scenarios, rake_fraction=0, rake_cap=0):
    """Robust label requires the same strict EV sign in every scenario."""
    if not isinstance(scenarios, (list, tuple)) or not scenarios:
        raise ValueError("nonempty scenarios required")
    results = []
    names = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {"name", "equity_interval"}:
            raise ValueError("scenario must contain name and equity_interval")
        name = scenario["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("invalid or duplicate scenario name")
        names.add(name)
        result = call_ev_bounds(pot_before_call=pot_before_call, call_cost=call_cost,
                                equity_interval=scenario["equity_interval"],
                                rake_fraction=rake_fraction, rake_cap=rake_cap)
        results.append({"name": name, "call_ev_interval": result["call_ev_interval"],
                        "break_even_equity": result["break_even_equity"]})
    lows = [s["call_ev_interval"][0] for s in results]
    highs = [s["call_ev_interval"][1] for s in results]
    decision = ("CALL_POSITIVE_ALL_SCENARIOS" if min(lows) > 0 else
                "FOLD_NONNEGATIVE_ALL_SCENARIOS" if max(highs) < 0 else
                "RANGE_SENSITIVE_OR_UNCERTAIN")
    return {"status": "CONDITIONAL_MODEL_ONLY", "decision": decision,
            "ev_envelope": [min(lows), max(highs)], "scenarios": results,
            "ranges_verified": False, "hand_error_verified": False,
            "gto_solution": False, "model_scope": "heads_up_no_future_bets_no_side_pots"}
