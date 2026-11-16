"""Offline conditional EV action envelopes. Not GTO or a verified-hand verdict."""
import math

def summarize_action_ev_scenarios(scenarios):
    """Compare fold/call/raise EV intervals across declared range scenarios."""
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 1000:
        raise ValueError('nonempty scenario list required (max 1000)')
    seen, normalized, actions = set(), [], None
    for s in scenarios:
        if not isinstance(s, dict):
            raise ValueError('invalid scenario')
        ident, source, ev = s.get('id'), s.get('range_source'), s.get('ev')
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError('missing or duplicate scenario id')
        if not isinstance(source, str) or not source.strip():
            raise ValueError('range source required')
        if not isinstance(ev, dict) or not ev or any(a not in ('fold', 'call', 'raise') for a in ev):
            raise ValueError('invalid action set')
        if actions is None:
            actions = frozenset(ev)
        elif actions != frozenset(ev):
            raise ValueError('inconsistent action sets')
        bounds = {}
        for action, interval in ev.items():
            if not isinstance(interval, (tuple, list)) or len(interval) != 2:
                raise ValueError('two EV endpoints required')
            lo, hi = interval
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in (lo, hi)) or lo > hi:
                raise ValueError('invalid EV interval')
            bounds[action] = [float(lo), float(hi)]
        normalized.append({'id': ident, 'ev': bounds})
        seen.add(ident)
    envelopes = {a: [min(s['ev'][a][0] for s in normalized), max(s['ev'][a][1] for s in normalized)] for a in sorted(actions)}
    dominant = [a for a in envelopes if all(envelopes[a][0] > envelopes[b][1] for b in envelopes if b != a)] if len(envelopes) > 1 else []
    return {'status': 'CONDITIONAL_SCENARIO_COMPARISON', 'scenario_count': len(normalized),
            'ev_envelopes': envelopes, 'robust_action': dominant[0] if dominant else None,
            'range_sensitive': not bool(dominant), 'scenario_ids': [s['id'] for s in normalized],
            'interpretation': 'scenario bounds, not statistical confidence',
            'hand_error_verified': False, 'gto_solution': False}
