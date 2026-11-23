"""Range sensitivity for hypothetical offline call EV; not a GTO solver."""
from .offline_conditional_call_ev import conditional_call_ev

def evaluate_call_scenarios(pot_before_call, call_cost, scenarios):
    """Scenarios require named, explicit ranges and conditional equity intervals."""
    if not isinstance(scenarios, (list, tuple)) or not 1 <= len(scenarios) <= 100:
        raise ValueError("provide 1-100 scenarios")
    seen, results = set(), []
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("scenario must be dict")
        name, assumption = item.get("name"), item.get("range_assumption")
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or name in seen:
            raise ValueError("scenario name must be unique")
        if not isinstance(assumption, str) or not assumption.strip():
            raise ValueError("range assumption required")
        if "equity_ci" not in item:
            raise ValueError("conditional equity interval required")
        seen.add(name)
        ev = conditional_call_ev(pot_before_call, call_cost, item.get("equity"), equity_ci=item["equity_ci"])
        results.append({
            "name": name, "range_assumption": assumption,
            "equity": item["equity"], "equity_ci": list(item["equity_ci"]),
            "call_ev_chips": ev["call_ev_chips"],
            "call_ev_interval_chips": ev["call_ev_interval_chips"],
            "break_even_equity": ev["break_even_equity"],
            "conditional_assumptions": ev["assumptions"],
        })
    lower = min(r["call_ev_interval_chips"][0] for r in results)
    upper = max(r["call_ev_interval_chips"][1] for r in results)
    tol = 1e-10 * max(1.0, abs(lower), abs(upper))
    classification = ("POSITIVE_IN_ALL_SUPPLIED_SCENARIOS" if lower > tol else
                      "NEGATIVE_IN_ALL_SUPPLIED_SCENARIOS" if upper < -tol else
                      "RANGE_OR_SAMPLING_SENSITIVE")
    return {
        "method": "HYPOTHETICAL_CONDITIONAL_CALL_RANGE_SENSITIVITY",
        "scenarios": results, "scenario_envelope_ev_chips": [lower, upper],
        "scenario_envelope_is_confidence_interval": False,
        "range_probabilities_known": False, "classification": classification,
        "strategic_verdict": "NOT_ESTABLISHED",
        "requires_video_evidence_review": True,
        "notes": "Only supplied ranges and sampling intervals; no GTO claim or inference of opponent range.",
    }
