"""Conservative offline Monte Carlo EV intervals; not GTO or an equity engine."""
import math

def conditional_mc_call_ev(pot_before_call, call_cost, scenario_samples, rake=0.0, confidence=0.95):
    """Hoeffding simultaneous bounds on independent pot-share samples in [0,1].

    Assumes fixed opponent ranges, heads-up, fixed rake, no side pots or future bets.
    Does not capture OCR uncertainty or uncertainty about opponent ranges.
    """
    def numeric(x):
        return type(x) in (int, float) and math.isfinite(x)
    if not all(numeric(x) for x in (pot_before_call, call_cost, rake, confidence)):
        raise ValueError('finite numeric parameters required')
    p, c, r = float(pot_before_call), float(call_cost), float(rake)
    if p < 0 or c <= 0 or r < 0 or r > p + c or not 0 < confidence < 1:
        raise ValueError('invalid pot, call, rake or confidence')
    if not isinstance(scenario_samples, dict) or not scenario_samples:
        raise ValueError('nonempty named scenarios required')
    output = {}
    for name, samples in scenario_samples.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(samples, (list, tuple)) or not samples:
            raise ValueError('invalid scenario or samples')
        if any(not numeric(x) or not 0 <= x <= 1 for x in samples):
            raise ValueError('pot shares must be finite and within [0,1]')
        n = len(samples)
        mean = math.fsum(samples) / n
        epsilon = math.sqrt(math.log(2 * len(scenario_samples) / (1 - confidence)) / (2 * n))
        lower, upper = max(0., mean - epsilon), min(1., mean + epsilon)
        total = p + c - r
        output[name] = {
            'samples': n, 'equity_estimate': mean,
            'equity_lower': lower, 'equity_upper': upper,
            'ev_estimate': mean * total - c,
            'ev_lower': lower * total - c, 'ev_upper': upper * total - c,
        }
    lo = min(v['ev_lower'] for v in output.values())
    hi = max(v['ev_upper'] for v in output.values())
    return {
        'method': 'hoeffding_union_bound_bounded_independent_samples',
        'confidence': confidence, 'scenarios': output, 'ev_envelope': [lo, hi],
        'conditional_signal': 'positive_across_scenarios' if lo > 0 else
                              'negative_across_scenarios' if hi < 0 else 'uncertain',
        'assumptions': ['independent pot-share samples per scenario',
                        'fixed specified opponent ranges', 'heads-up call',
                        'no future betting or side pots', 'fixed rake'],
        'range_model_uncertainty_included': False,
        'ocr_uncertainty_included': False,
        'gto_solution': False, 'strategic_verdict_allowed': False,
    }
