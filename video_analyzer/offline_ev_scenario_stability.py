"""Conservative conditional EV comparison across declared offline range scenarios.

Intervals are conditional estimates, not GTO guarantees or evidence of a hand error.
"""
import math

ACTIONS = frozenset({'fold', 'call', 'raise'})


def compare_scenarios(scenarios):
    """Strictly compare actions within each scenario, then check cross-range stability."""
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 1000:
        raise ValueError('expected 1..1000 scenarios')
    ids, results, action_set = set(), [], None
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError('scenario must be an object')
        ident, source, ev = scenario.get('id'), scenario.get('range_source'), scenario.get('ev')
        if not isinstance(ident, str) or not ident.strip() or ident.strip() in ids:
            raise ValueError('scenario id missing or duplicate')
        if not isinstance(source, str) or not source.strip():
            raise ValueError('range provenance required')
        if not isinstance(ev, dict) or not ev or not set(ev).issubset(ACTIONS):
            raise ValueError('invalid actions')
        if action_set is None:
            action_set = frozenset(ev)
        elif action_set != frozenset(ev):
            raise ValueError('actions differ across scenarios')
        for interval in ev.values():
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                raise ValueError('interval must have two endpoints')
            lo, hi = interval
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in (lo, hi)) or lo > hi:
                raise ValueError('invalid interval')
        winner = next((a for a in ev if all(ev[a][0] > ev[b][1] for b in ev if b != a)), None) if len(ev) > 1 else None
        results.append({'id': ident.strip(), 'strict_winner': winner})
        ids.add(ident.strip())
    winners = [r['strict_winner'] for r in results]
    stable = winners[0] if len(winners) >= 2 and winners[0] is not None and all(w == winners[0] for w in winners) else None
    return {'status': 'CONDITIONAL_ONLY', 'scenarios': results, 'stable_action': stable,
            'range_sensitive_or_inconclusive': stable is None,
            'cross_range_comparison_available': len(winners) >= 2,
            'hand_error_verified': False, 'gto_solution': False,
            'interpretation': 'strict interval comparison under declared ranges; not a statistical confidence interval'}
