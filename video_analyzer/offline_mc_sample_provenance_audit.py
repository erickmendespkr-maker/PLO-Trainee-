"""Audit sample provenance in offline conditional Monte Carlo reports.

This is not an equity engine and cannot establish range correctness or GTO.
"""
import hashlib
import json
import math


def audit_sample_provenance(report, samples_by_scenario):
    if type(report) is not dict or type(samples_by_scenario) is not dict:
        raise ValueError("report and samples must be dictionaries")
    if report.get("schema_version") != 1:
        raise ValueError("unsupported report schema")
    if report.get("equity_engine_executed") is not False or report.get("strategic_verdict_allowed") is not False or report.get("gto_solution") is not False:
        raise ValueError("unsupported verification claim")
    provenance = report.get("sampling_provenance")
    calculation = report.get("calculation")
    if type(provenance) is not dict or not provenance or type(calculation) is not dict:
        raise ValueError("missing provenance or calculation")
    observed = calculation.get("scenarios")
    if type(observed) is not dict or set(provenance) != set(samples_by_scenario) or set(provenance) != set(observed):
        raise ValueError("scenario mismatch")
    if calculation.get("strategic_verdict_allowed") is not False or calculation.get("gto_solution") is not False:
        raise ValueError("unsupported calculation claim")
    for name, shares in samples_by_scenario.items():
        meta, result = provenance[name], observed[name]
        if type(meta) is not dict or type(result) is not dict or type(shares) not in (tuple, list) or not shares:
            raise ValueError("invalid scenario")
        if any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares):
            raise ValueError("invalid shares")
        seed = meta.get("seed")
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("invalid seed")
        if type(meta.get("range_description")) is not str or not meta["range_description"].strip():
            raise ValueError("missing range hypothesis")
        normalized = [float(x) for x in shares]
        digest = hashlib.sha256(json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if meta.get("samples_sha256") != digest or type(meta.get("sample_count")) is not int or meta["sample_count"] != len(shares):
            raise ValueError("sample provenance mismatch")
        if type(result.get("samples")) is not int or result["samples"] != len(shares):
            raise ValueError("reported sample count mismatch")
        equity = result.get("equity_estimate")
        if type(equity) not in (int, float) or not math.isfinite(equity) or not math.isclose(equity, math.fsum(normalized)/len(shares), rel_tol=0, abs_tol=1e-10):
            raise ValueError("reported equity mismatch")
        for key in ("equity_lower", "equity_upper", "ev_lower", "ev_estimate", "ev_upper"):
            v = result.get(key)
            if type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError("invalid reported result")
        if not 0 <= result["equity_lower"] <= equity + 1e-10 or not equity - 1e-10 <= result["equity_upper"] <= 1:
            raise ValueError("invalid equity bounds")
        if not result["ev_lower"] <= result["ev_estimate"] <= result["ev_upper"]:
            raise ValueError("invalid EV bounds")
    return {"sample_hashes_verified": len(provenance), "equity_means_verified": True,
            "ev_arithmetic_verified": False, "range_assumptions_verified": False,
            "equity_engine_executed": False, "strategic_verdict_allowed": False}
