"""Bounded-confidence scenarios for offline PLO equity review.

Consumes independent simulator showdown shares; never infers hidden cards or GTO.
"""
import math

try:
    from .offline_equity_ci_audit import bounded_share_interval
except ImportError:
    from offline_equity_ci_audit import bounded_share_interval


def bounded_equity_scenario(name, shares, *, seed, range_assumption, confidence=0.95):
    """Estimate equity conditional on iid samples from one fixed range model."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("scenario name required")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not isinstance(range_assumption, str) or not range_assumption.strip():
        raise ValueError("explicit range assumption required")
    if not isinstance(shares, (list, tuple)) or not 30 <= len(shares) <= 1000000:
        raise ValueError("30-1000000 showdown shares required")
    summary = bounded_share_interval(shares, confidence=confidence)
    lo, hi = summary["equity_ci"]
    width = hi - lo
    return {
        "name": name.strip(), "range_assumption": range_assumption.strip(),
        "equity": summary["equity"], "equity_ci": [lo, hi],
        "seed": seed, "samples": summary["samples"],
        "confidence_level": summary["confidence_level"],
        "method": summary["method"],
        "status": "INSUFFICIENT_PRECISION" if width > 0.25 else "CONSERVATIVE_CI",
        "range_uncertainty_included": False, "gto_solution": False,
        "assumptions": list(summary["assumptions"]),
        "notes": "Conditional iid confidence interval; no inference of unseen cards or unknown ranges.",
    }


def to_call_scenario(summary):
    """Expose only validated fields for conditional call EV sensitivity."""
    if not isinstance(summary, dict) or summary.get("method") != "EMPIRICAL_BERNSTEIN_BOUNDED_SHARES":
        raise ValueError("bounded confidence summary required")
    if summary.get("status") != "CONSERVATIVE_CI":
        raise ValueError("insufficient precision")
    equity = summary.get("equity")
    ci = summary.get("equity_ci")
    if (not isinstance(equity, (int, float)) or isinstance(equity, bool)
            or not math.isfinite(equity) or not isinstance(ci, (list, tuple)) or len(ci) != 2
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in ci)
            or not 0 <= ci[0] <= equity <= ci[1] <= 1):
        raise ValueError("invalid equity interval")
    if not isinstance(summary.get("range_assumption"), str) or not summary["range_assumption"].strip():
        raise ValueError("range assumption required")
    if not isinstance(summary.get("name"), str) or not summary["name"].strip():
        raise ValueError("name required")
    return {"name": summary["name"], "range_assumption": summary["range_assumption"],
            "equity": equity, "equity_ci": list(ci)}
