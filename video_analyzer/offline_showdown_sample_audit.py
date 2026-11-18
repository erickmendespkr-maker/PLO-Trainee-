"""Audit offline showdown samples: conditional EV and sampling-only uncertainty."""
from math import fsum, isfinite, sqrt, log

def audit_showdown_samples(pot_before_call, call_cost, hero_shares, *, rake=0.0, range_label=None, seed=None):
    """95% Hoeffding bound for iid sampled shares in [0,1] from a fixed range.

    Does not quantify range uncertainty or claim a GTO solution.
    """
    for v in (pot_before_call, call_cost, rake):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v):
            raise ValueError('monetary inputs must be finite numbers')
    p, c, r = float(pot_before_call), float(call_cost), float(rake)
    if p < 0 or c <= 0 or r < 0 or r > p + c:
        raise ValueError('invalid pot/call/rake')
    if not isinstance(hero_shares, (list, tuple)) or not hero_shares:
        raise ValueError('hero_shares must be a nonempty sequence')
    if range_label is not None and (not isinstance(range_label, str) or not range_label.strip()):
        raise ValueError('range_label must be a nonempty string')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        raise ValueError('seed must be a nonnegative integer')
    shares = []
    for s in hero_shares:
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not isfinite(s) or not 0 <= s <= 1:
            raise ValueError('shares must be finite fractions in [0,1]')
        shares.append(float(s))
    n = len(shares)
    mean = fsum(shares) / n
    epsilon = sqrt(log(40.0) / (2 * n))
    gross = p + c - r
    def payoff(s):
        return s * gross - c
    return {
        'status': 'HYPOTHETICAL_ONLY',
        'sample_count': n,
        'seed': seed,
        'range_label': range_label,
        'mean_hero_share': mean,
        'call_ev': payoff(mean),
        'fold_ev': 0.0,
        'call_ev_95pct_hoeffding_interval': [
            payoff(max(0.0, mean - epsilon)),
            payoff(min(1.0, mean + epsilon)),
        ],
        'confidence_scope': 'iid_sampling_only_given_fixed_range',
        'range_uncertainty_quantified': False,
        'assumptions': ['iid_samples', 'fixed_declared_range', 'showdown_only', 'no_future_betting', 'fixed_rake'],
        'gto_claim_permitted': False,
        'automatic_blunder_label_permitted': False,
    }
