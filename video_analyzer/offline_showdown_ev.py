"""Offline heads-up showdown EV from explicit outcome probabilities.

Not a solver or a range estimator. Fold baseline is zero; no future betting,
side pots or multiway pots. Rake is applied to gross pot before splitting.
"""
from math import isfinite, fsum


def showdown_call_ev(pot_before_call, call_cost, outcomes, *, rake=0.0):
    """Return conditional call EV for exhaustive showdown outcomes.

    Each outcome has probability and hero_share in [0,1]. hero_share is
    the fraction of the final pot received (0 loss, 1 win, 0.5 split).
    The rake is a fixed amount taken from the final pot in every outcome;
    caller must choose an appropriate model (no-flop-no-drop not modeled).
    """
    values = (pot_before_call, call_cost, rake)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError('monetary inputs must be finite numbers')
    p, c, r = map(float, values)
    if p < 0 or c <= 0 or r < 0 or r > p + c:
        raise ValueError('invalid pot, call or rake')
    if not isinstance(outcomes, list) or not outcomes:
        raise ValueError('outcomes must be a nonempty list')
    probabilities, shares, breakdown = [], [], []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise ValueError('invalid outcome')
        q, share = outcome.get('probability'), outcome.get('hero_share')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (q, share)):
            raise ValueError('probability and share must be finite numbers')
        if not 0 <= q <= 1 or not 0 <= share <= 1:
            raise ValueError('probability or share outside [0,1]')
        probabilities.append(float(q))
        shares.append(float(share))
    if not abs(fsum(probabilities) - 1.0) <= 1e-9:
        raise ValueError('outcome probabilities must sum to one')
    total = p + c
    for q, share in zip(probabilities, shares):
        payoff = share * (total - r) - c
        breakdown.append({'probability': q, 'hero_share': share, 'net_payoff': payoff})
    return {
        'status': 'HYPOTHETICAL_ONLY',
        'call_ev': fsum(x['probability'] * x['net_payoff'] for x in breakdown),
        'fold_ev': 0.0,
        'pot_before_call': p,
        'call_cost': c,
        'rake_from_final_pot': r,
        'outcomes': breakdown,
        'assumptions': ['heads_up', 'showdown_only', 'no_future_betting', 'no_side_pots', 'fixed_rake_from_final_pot'],
        'gto_claim_permitted': False,
        'automatic_blunder_label_permitted': False,
    }
