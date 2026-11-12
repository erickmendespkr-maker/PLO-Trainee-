"""Offline, conditional heads-up call EV sensitivity; NOT a GTO solver.

P is the pot before calling; C is the additional cost. No rake,
side pots, future betting or multiway action are modeled. Equity bounds
are conditional Monte Carlo uncertainty, not uncertainty about ranges.
"""
from __future__ import annotations
import math


def _number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'invalid {name}')
    return float(value)


def evaluate_call_scenarios(pot_bb, call_bb, scenarios):
    """Evaluate user-supplied equity estimates and intervals for each assumed range.

    Each scenario: {range_id, equity, equity_ci:[low, high], iterations, seed}.
    Returns conditional EV and sensitivity; never recommends a move.
    """
    pot = _number(pot_bb, 'pot_bb', 0, 1e7)
    cost = _number(call_bb, 'call_bb', 1e-9, 1e7)
    if type(scenarios) is not list or not 2 <= len(scenarios) <= 24:
        raise ValueError('2..24 scenarios required')
    seen = set()
    results = []
    for scenario in scenarios:
        if type(scenario) is not dict:
            raise ValueError('invalid scenario')
        rid = scenario.get('range_id')
        if type(rid) is not str or not 1 <= len(rid) <= 80 or not all(c.isascii() and (c.isalnum() or c in '_-.') for c in rid) or rid in seen:
            raise ValueError('invalid or duplicate range_id')
        seen.add(rid)
        q = _number(scenario.get('equity'), 'equity', 0, 1)
        ci = scenario.get('equity_ci')
        if type(ci) is not list or len(ci) != 2:
            raise ValueError('invalid equity_ci')
        lo = _number(ci[0], 'equity_ci lower', 0, 1)
        hi = _number(ci[1], 'equity_ci upper', 0, 1)
        if not lo <= q <= hi:
            raise ValueError('equity outside interval')
        iterations = scenario.get('iterations')
        seed = scenario.get('seed')
        if type(iterations) is not int or not 1 <= iterations <= 100_000_000 or type(seed) is not int or not 0 <= seed <= 2**64-1:
            raise ValueError('invalid Monte Carlo metadata')
        ev = q * (pot + cost) - cost
        bounds = [lo * (pot + cost) - cost, hi * (pot + cost) - cost]
        label = 'positive_under_interval' if bounds[0] > 0 else 'negative_under_interval' if bounds[1] < 0 else 'uncertain_or_break_even'
        results.append({'range_id': rid, 'equity': q, 'equity_ci_conditional': [lo, hi], 'ev_call_bb': ev, 'ev_ci_conditional_bb': bounds, 'conditional_label': label, 'iterations': iterations, 'seed': seed})
    labels = {r['conditional_label'] for r in results}
    return {'schema_version': 1, 'analysis_status': 'HYPOTHETICAL_RANGE_SENSITIVITY_ONLY',
            'pot_before_call_bb': pot, 'call_cost_bb': cost, 'break_even_equity': cost / (pot + cost),
            'scenarios': results, 'range_sensitive': labels != {'positive_under_interval'} and labels != {'negative_under_interval'},
            'ev_envelope_bb': [min(r['ev_ci_conditional_bb'][0] for r in results), max(r['ev_ci_conditional_bb'][1] for r in results)],
            'range_uncertainty_included_in_ci': False, 'gto_solution': False, 'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
            'warning': 'Heads-up simplified call only; no rake, side pots, multiway or future action. Ranges are assumptions; CIs are conditional on each range, not uncertainty about ranges. Not GTO or a strategic verdict.'}
