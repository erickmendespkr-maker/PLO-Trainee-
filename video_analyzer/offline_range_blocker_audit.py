"""Preflight audit of *hypothetical* weighted ranges against human-declared cards.

This does not verify the video, infer opponent ranges, or grade any action.
The Monte Carlo engine conditions weighted ranges on visible blockers; this
module makes that conditioning explicit before the EV bundle is generated.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from offline_plo_equity_monte_carlo import cards, require


def _fingerprint(model):
    payload = json.dumps(model, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False)
    return sha256(payload.encode('utf-8')).hexdigest()


def _one(model, variant, known):
    require(type(model) is dict and model.get('kind') in ('uniform', 'weighted_combos'),
            'invalid range model')
    require(set(model) == ({'kind'} if model['kind'] == 'uniform' else {'kind', 'combos'}),
            'unexpected range fields')
    result = {'kind': model['kind'], 'model_sha256': _fingerprint(model),
              'conditioned_on_human_declared_cards': True,
              'range_accuracy_verified': False}
    if model['kind'] == 'uniform':
        result.update({'supplied_combos': None, 'eligible_combos': None,
                       'blocked_combos': None, 'blocked_weight_fraction': None,
                       'warning': 'Uniform range excludes visible cards; not an observed range.'})
        return result, None
    combos = model['combos']
    require(type(combos) is list and 1 <= len(combos) <= 1000,
            'weighted range must contain 1..1000 combos')
    expected = 5 if variant == 'PLO5' else 6
    seen, eligible = set(), set()
    total_weight = legal_weight = 0.0
    blocked = 0
    for item in combos:
        require(type(item) is dict and set(item) == {'cards', 'weight'},
                'invalid weighted combo')
        hand = cards(item['cards'], expected)
        key = tuple(sorted(hand))
        require(key not in seen, 'duplicate weighted combo')
        seen.add(key)
        weight = item['weight']
        require(type(weight) in (int, float) and math.isfinite(weight) and
                0 < weight <= 1_000_000, 'invalid combo weight')
        total_weight += float(weight)
        require(math.isfinite(total_weight), 'range weight overflow')
        if known.intersection(hand):
            blocked += 1
        else:
            eligible.add(key)
            legal_weight += float(weight)
    require(eligible and legal_weight > 0, 'weighted range has no legal combos after blockers')
    fraction = (total_weight - legal_weight) / total_weight
    result.update({'supplied_combos': len(combos), 'eligible_combos': len(eligible),
                   'blocked_combos': blocked, 'blocked_weight_fraction': fraction,
                   'warning': ('At least half the supplied range weight is blocked; '
                               'remaining weights are renormalized, not observed.'
                               if fraction >= .5 else
                               'Visible-card blockers removed; remaining weights are '
                               'renormalized, not observed.')})
    return result, eligible


def audit(variant, hero_cards, board_cards, hypotheses):
    """Return bounded, JSON-safe diagnostics; never modify the supplied ranges."""
    require(variant in ('PLO5', 'PLO6'), 'invalid PLO variant')
    hero = cards(hero_cards, 5 if variant == 'PLO5' else 6)
    board = cards(board_cards)
    require(3 <= len(board) <= 5 and len(set(hero + board)) == len(hero + board),
            'invalid declared cards or overlap')
    require(type(hypotheses) is list and 1 <= len(hypotheses) <= 5,
            'invalid hypothesis count')
    known = set(hero + board)
    rows = []
    for h in hypotheses:
        require(type(h) is dict and type(h.get('label')) is str,
                'invalid hypothesis')
        call, a = _one(h.get('call_model'), variant, known)
        raised, b = _one(h.get('raise_called_model'), variant, known)
        overlap = None if a is None or b is None else len(a & b)
        rows.append({'label': h['label'], 'call': call, 'raise_called': raised,
                     'eligible_combo_overlap_count': overlap,
                     'conditional_ranges_may_differ_by_design': True,
                     'warning': ('Disjoint legal call/raise ranges: allowed as separate '
                                 'assumptions; not evidence of opponent behavior.'
                                 if overlap == 0 else None)})
    return {'schema_version': 1,
            'analysis_status': 'hypothetical_range_blocker_preflight_only',
            'video_or_ocr_verified': False,
            'range_accuracy_verified': False,
            'blocked_combos_silently_discarded': False,
            'rows': rows}
