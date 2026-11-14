"""Offline Hoeffding uncertainty for bounded showdown shares; not GTO."""
import math
from .offline_call_ev_scenarios import evaluate_call_scenarios

def equity_interval_from_shares(*, shares, confidence=0.95):
    """IID draws from one fixed hypothetical range; does not cover range or OCR errors."""
    if not isinstance(shares, (list, tuple)) or not shares:
        raise ValueError("nonempty sample shares required")
    if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("invalid confidence")
    if any(type(s) not in (float, int) or not math.isfinite(s) or not 0 <= s <= 1 for s in shares):
        raise ValueError("shares must be finite fractions in [0,1]")
    n = len(shares)
    mean = math.fsum(shares) / n
    radius = math.sqrt(math.log(2 / (1 - confidence)) / (2 * n))
    return {"equity_estimate": mean,
            "equity_interval": [max(0., mean-radius), min(1., mean+radius)],
            "sample_count": n, "confidence": float(confidence),
            "interval_method": "two_sided_hoeffding_iid_bounded_shares",
            "sampling_assumption": "IID draws from fixed hypothetical opponent range",
            "range_uncertainty_included": False, "ocr_uncertainty_included": False,
            "gto_solution": False}

def evaluate_sampled_call_scenarios(*, pot_before_call, call_cost, scenarios,
                                    confidence=0.95, rake_fraction=0, rake_cap=0):
    """Bonferroni simultaneous sampling bounds; not a probability ranges are correct."""
    if not isinstance(scenarios, (list, tuple)) or not scenarios:
        raise ValueError("nonempty scenarios required")
    if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("invalid confidence")
    per_confidence = 1 - (1 - confidence) / len(scenarios)
    intervals, enriched = [], []
    for s in scenarios:
        if not isinstance(s, dict) or set(s) != {"name", "shares"}:
            raise ValueError("each scenario needs name and shares")
        bound = equity_interval_from_shares(shares=s["shares"], confidence=per_confidence)
        intervals.append({"name": s["name"], "equity_interval": bound["equity_interval"]})
        enriched.append({"name": s["name"], **bound})
    ev = evaluate_call_scenarios(pot_before_call=pot_before_call, call_cost=call_cost,
                                 scenarios=intervals, rake_fraction=rake_fraction,
                                 rake_cap=rake_cap)
    return {**ev, "sampled_scenarios": enriched,
            "joint_sampling_confidence": float(confidence),
            "joint_method": "Bonferroni_union_bound_over_scenarios",
            "range_uncertainty_included": False, "ocr_uncertainty_included": False,
            "hand_error_verified": False, "gto_solution": False}
