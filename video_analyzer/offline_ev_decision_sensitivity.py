"""Conservative sensitivity audit for hypothetical offline EV comparisons; not GTO."""
import math

def compare_scenarios(scenarios, *, min_gap=0.0):
    """Require interval dominance in every scenario before preferring an action."""
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("nonempty scenarios required")
    if type(min_gap) not in (int, float) or not math.isfinite(min_gap) or min_gap < 0:
        raise ValueError("invalid min_gap")
    actions = ("fold", "call", "raise")
    reports, robust, ids = [], set(actions), set()
    for item in scenarios:
        if not isinstance(item, dict) or set(item) != {"scenario_id", "assumptions", "ev_intervals"}:
            raise ValueError("invalid scenario schema")
        sid, assumptions, intervals = item["scenario_id"], item["assumptions"], item["ev_intervals"]
        if not isinstance(sid, str) or not sid.strip() or sid in ids:
            raise ValueError("invalid or duplicate scenario ID")
        ids.add(sid)
        if not isinstance(assumptions, dict) or not assumptions or not all(isinstance(k, str) and k and isinstance(v, (str, int, float, bool)) and not (isinstance(v, float) and not math.isfinite(v)) for k, v in assumptions.items()):
            raise ValueError("explicit finite assumptions required")
        if not isinstance(intervals, dict) or set(intervals) != set(actions):
            raise ValueError("fold/call/raise intervals required")
        normalized = {}
        for action in actions:
            pair = intervals[action]
            if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in pair) or pair[0] > pair[1]:
                raise ValueError("invalid EV interval")
            normalized[action] = [float(pair[0]), float(pair[1])]
        winners = [a for a in actions if all(normalized[a][0] > normalized[b][1] + min_gap for b in actions if b != a)]
        robust.intersection_update(winners)
        reports.append({"scenario_id": sid, "assumptions": assumptions, "ev_intervals": normalized, "robust_winner": winners[0] if winners else None})
    winner = next(iter(robust)) if len(robust) == 1 else None
    return {"status": "CONDITIONAL_EV_COMPARISON_ONLY", "preferred_action": winner,
            "classification": "ROBUST_WITHIN_GIVEN_SCENARIOS" if winner else "RANGE_SENSITIVE_OR_UNCERTAIN",
            "min_gap": float(min_gap), "scenarios": reports,
            "ranges_verified": False, "gto_solution": False, "hand_error_verified": False}
