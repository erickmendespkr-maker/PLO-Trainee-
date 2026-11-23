"""Convert reproducible Monte Carlo showdown shares into conditional equity scenarios.

Input shares must be showdown fractions in [0,1] (0 loss, 1 win, 1/k split).
This module does not simulate cards, infer ranges or calculate a GTO solution.
"""
import math
from statistics import NormalDist


def summarize_showdown_shares(shares, *, seed, range_assumption, confidence=0.95):
    """Return mean equity and approximate normal CI for bounded showdown shares.

    CI describes Monte Carlo sampling error conditional on the supplied range.
    A normal approximation is unreliable for rare events / boundary samples;
    in those cases status is INSUFFICIENT_PRECISION and CI is conservatively [0,1].
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not isinstance(range_assumption, str) or not range_assumption.strip():
        raise ValueError("explicit range assumption required")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0.5 < confidence < 1:
        raise ValueError("invalid confidence level")
    if not isinstance(shares, (list, tuple)) or not 30 <= len(shares) <= 1000000:
        raise ValueError("30-1000000 showdown shares required")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares):
        raise ValueError("showdown shares must be finite fractions in [0,1]")
    n = len(shares)
    mean = math.fsum(shares) / n
    variance = math.fsum((x - mean) ** 2 for x in shares) / (n - 1)
    stderr = math.sqrt(variance / n)
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    # Degenerate samples do not establish zero uncertainty: rare outcomes may be missed.
    degenerate = variance == 0
    lo, hi = ((0.0, 1.0) if degenerate else
              (max(0.0, mean - z * stderr), min(1.0, mean + z * stderr)))
    return {
        "method": "MONTE_CARLO_SHOWDOWN_SHARE_NORMAL_APPROX",
        "equity": mean, "equity_ci": [lo, hi], "confidence_level": float(confidence),
        "samples": n, "seed": seed, "range_assumption": range_assumption,
        "standard_error": stderr, "status": "INSUFFICIENT_PRECISION" if degenerate else "APPROXIMATE_CI",
        "range_uncertainty_included": False, "gto_solution": False,
        "notes": "Normal approximation conditional on supplied range; no range-model uncertainty. Degenerate samples use [0,1].",
    }


def to_call_scenario(name, summary):
    """Adapt a validated equity summary for offline_call_range_sensitivity."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("scenario name required")
    if not isinstance(summary, dict) or summary.get("method") != "MONTE_CARLO_SHOWDOWN_SHARE_NORMAL_APPROX":
        raise ValueError("validated Monte Carlo summary required")
    if summary.get("status") != "APPROXIMATE_CI":
        raise ValueError("insufficient Monte Carlo precision")
    return {"name": name, "range_assumption": summary["range_assumption"],
            "equity": summary["equity"], "equity_ci": list(summary["equity_ci"])}
