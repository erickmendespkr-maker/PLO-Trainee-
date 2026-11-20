"""Bind hypothetical EV monetary assumptions; integrity is not video verification."""
import hashlib
import json
import math

def bind_monetary_assumptions(*, pot_before_call, call_cost, rake=0.0, currency_unit='chips'):
    values = (pot_before_call, call_cost, rake)
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
        raise ValueError('monetary values must be finite numbers, not booleans')
    p, c, r = map(float, values)
    if p < 0 or c <= 0 or r < 0 or r > p + c:
        raise ValueError('invalid heads-up single-call monetary assumptions')
    if currency_unit not in ('chips', 'bb'):
        raise ValueError('unit must be chips or bb')
    payload = {'model': 'hypothetical_heads_up_single_call', 'pot_before_call': p,
               'call_cost': c, 'rake': r, 'unit': currency_unit}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return {'assumptions': payload, 'sha256': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            'source': 'caller_supplied_not_video_verified'}

def audit_monetary_binding(binding, *, pot_before_call, call_cost, rake=0.0, currency_unit='chips'):
    if type(binding) is not dict or set(binding) != {'assumptions', 'sha256', 'source'}:
        raise ValueError('invalid binding schema')
    expected = bind_monetary_assumptions(pot_before_call=pot_before_call,
        call_cost=call_cost, rake=rake, currency_unit=currency_unit)
    if binding != expected:
        raise ValueError('monetary assumptions differ from bound record')
    return {'monetary_assumptions_integrity_verified': True,
            'monetary_values_video_verified': False}
