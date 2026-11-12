"""Conservative conditional call/fold EV bounds for offline PLO reviews.

This is algebra on externally supplied equity bounds, not a poker solver.
Intervals reflect assumptions and must never be called GTO or video evidence.
"""
import math


def number(x, lo, hi):
    return type(x) in (int, float) and math.isfinite(x) and lo <= x <= hi


def evaluate(pot_before_call_bb, call_cost_bb, scenarios):
    p, c = pot_before_call_bb, call_cost_bb
    if not number(p, 0, 1e6) or not number(c, 1e-9, 1e6):
        raise ValueError('Invalid pot or call cost')
    if type(scenarios) is not list or not 2 <= len(scenarios) <= 12:
        raise ValueError('Expected 2 to 12 distinct hypothetical ranges')
    results, seen = [], set()
    for s in scenarios:
        if type(s) is not dict or set(s) != {'range_id', 'equity_interval_conditional'}:
            raise ValueError('Invalid scenario fields')
        name, interval = s['range_id'], s['equity_interval_conditional']
        if type(name) is not str or not 1 <= len(name) <= 80 or not all(ch.isascii() and (ch.isalnum() or ch in '._-') for ch in name) or name in seen:
            raise ValueError('Invalid or duplicate range identifier')
        seen.add(name)
        if type(interval) is not list or len(interval) != 2 or not all(number(q, 0, 1) for q in interval) or interval[0] > interval[1]:
            raise ValueError('Invalid conditional equity interval')
        lo, hi = [q * (p+c) - c for q in interval]
        results.append({'range_id': name, 'ev_call_interval_bb': [lo, hi],
                        'call_vs_fold': 'call' if lo > 0 else ('fold' if hi < 0 else 'indeterminate')})
    low = min(r['ev_call_interval_bb'][0] for r in results)
    high = max(r['ev_call_interval_bb'][1] for r in results)
    verdict = 'call_under_all_supplied_ranges' if low > 0 else ('fold_under_all_supplied_ranges' if high < 0 else 'range_sensitive_or_uncertain')
    return {'schema_version': 1, 'analysis_status': 'hypothetical_conditional_bounds_only',
            'break_even_equity': c/(p+c), 'ev_call_scenario_envelope_bb': [low, high],
            'conditional_comparison': verdict, 'scenarios': results,
            'source_hand_reconstruction_verified': False, 'strategic_error_established': False,
            'gto_solution': False, 'range_uncertainty_quantified': False,
            'warning': 'Bounds condition on supplied ranges; envelope is not a statistical confidence interval or a verified poker verdict.'}
