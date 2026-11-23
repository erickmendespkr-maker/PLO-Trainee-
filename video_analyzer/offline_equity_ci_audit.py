"""Conservative finite-sample interval for bounded showdown shares.

Independent of card simulation. Assumes iid shares from one fixed range model.
"""
import math


def bounded_share_interval(shares, confidence=0.95):
    """Two-sided empirical Bernstein interval for iid bounded [0,1] samples."""
    if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not math.isfinite(confidence) or not 0.5 < confidence < 1:
        raise ValueError("invalid confidence")
    if not isinstance(shares, (tuple, list)) or len(shares) < 2:
        raise ValueError("at least two shares required")
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares):
        raise ValueError("shares must be finite in [0,1]")
    n = len(shares)
    mean = math.fsum(shares) / n
    variance = math.fsum((x - mean) ** 2 for x in shares) / (n - 1)
    # Maurer-Pontil empirical Bernstein bound, two-sided via union bound.
    log_term = math.log(4 / (1 - confidence))
    radius = math.sqrt(2 * variance * log_term / n) + 7 * log_term / (3 * (n - 1))
    return {
        "method": "EMPIRICAL_BERNSTEIN_BOUNDED_SHARES",
        "equity": mean,
        "equity_ci": [max(0., mean - radius), min(1., mean + radius)],
        "samples": n,
        "confidence_level": float(confidence),
        "range_uncertainty_included": False,
        "gto_solution": False,
        "assumptions": ["iid_showdown_shares", "fixed_range_distribution", "bounded_shares_0_to_1"],
    }
