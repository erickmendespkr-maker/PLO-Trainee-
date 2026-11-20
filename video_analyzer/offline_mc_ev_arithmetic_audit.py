"""Independent arithmetic audit of hypothetical heads-up call EV; not GTO."""
import math

def audit_mc_ev_arithmetic(report, samples_by_scenario, *, pot_before_call, call_cost, rake=0.0):
    """Verify arithmetic, not sampling independence, ranges, OCR or poker rules."""
    def finite(x):
        return type(x) in (int, float) and math.isfinite(x)
    if type(report) is not dict or type(samples_by_scenario) is not dict or not samples_by_scenario:
        raise ValueError("invalid report or samples")
    if any(not finite(x) for x in (pot_before_call, call_cost, rake)):
        raise ValueError("nonfinite monetary input")
    p, c, r = float(pot_before_call), float(call_cost), float(rake)
    if p < 0 or c <= 0 or r < 0 or r > p + c:
        raise ValueError("invalid monetary input")
    if report.get("schema_version") != 1 or report.get("model_scope") != "hypothetical_heads_up_single_call":
        raise ValueError("unsupported report scope")
    if any(report.get(k) is not False for k in ("gto_solution", "strategic_verdict_allowed", "equity_engine_executed")):
        raise ValueError("unsupported verification claim")
    calc = report.get("calculation")
    if type(calc) is not dict or calc.get("method") != "hoeffding_union_bound_bounded_independent_samples":
        raise ValueError("unsupported calculation")
    confidence = calc.get("confidence")
    if not finite(confidence) or not 0 < confidence < 1:
        raise ValueError("invalid confidence")
    observed = calc.get("scenarios")
    if type(observed) is not dict or set(observed) != set(samples_by_scenario):
        raise ValueError("scenario mismatch")
    if calc.get("gto_solution") is not False or calc.get("strategic_verdict_allowed") is not False:
        raise ValueError("unsupported calculation claim")
    total = p + c - r
    lower_evs, upper_evs = [], []
    for name, shares in samples_by_scenario.items():
        if type(shares) not in (list, tuple) or not shares or any(not finite(x) or not 0 <= x <= 1 for x in shares):
            raise ValueError("invalid pot shares")
        entry = observed[name]
        if type(entry) is not dict or type(entry.get("samples")) is not int or entry["samples"] != len(shares):
            raise ValueError("sample count mismatch")
        mean = math.fsum(shares) / len(shares)
        eps = math.sqrt(math.log(2 * len(samples_by_scenario) / (1 - confidence)) / (2 * len(shares)))
        lo, hi = max(0., mean - eps), min(1., mean + eps)
        expected = {"equity_estimate": mean, "equity_lower": lo, "equity_upper": hi,
                    "ev_estimate": mean * total - c, "ev_lower": lo * total - c,
                    "ev_upper": hi * total - c}
        for key, value in expected.items():
            actual = entry.get(key)
            if not finite(actual) or not math.isclose(actual, value, rel_tol=1e-12, abs_tol=1e-10):
                raise ValueError("arithmetic mismatch: " + str(name) + "/" + key)
        lower_evs.append(expected["ev_lower"])
        upper_evs.append(expected["ev_upper"])
    envelope = calc.get("ev_envelope")
    if type(envelope) not in (list, tuple) or len(envelope) != 2 or any(not finite(x) for x in envelope):
        raise ValueError("invalid envelope")
    if not math.isclose(envelope[0], min(lower_evs), rel_tol=1e-12, abs_tol=1e-10) or not math.isclose(envelope[1], max(upper_evs), rel_tol=1e-12, abs_tol=1e-10):
        raise ValueError("envelope mismatch")
    signal = "positive_across_scenarios" if min(lower_evs) > 0 else "negative_across_scenarios" if max(upper_evs) < 0 else "uncertain"
    if calc.get("conditional_signal") != signal:
        raise ValueError("conditional signal mismatch")
    if calc.get("range_model_uncertainty_included") is not False or calc.get("ocr_uncertainty_included") is not False:
        raise ValueError("unsupported uncertainty claim")
    return {"scenario_count": len(samples_by_scenario), "ev_arithmetic_verified": True,
            "sampling_independence_verified": False, "range_assumptions_verified": False,
            "ocr_verified": False, "equity_engine_executed": False,
            "strategic_verdict_allowed": False}
