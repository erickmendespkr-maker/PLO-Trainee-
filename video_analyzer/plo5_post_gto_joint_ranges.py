"""Exact rational HU range reach along a modeled river history, offline only."""
from fractions import Fraction
from math import gcd, lcm, isfinite
from plo5_post_gto_context import normalize, identity
from plo5_pre_gto_context import cards, need


def condition_path(context, data, history, known=None):
    c = normalize(context)
    need(len(c['seats']) == 2 and len(c['board']) == 5, 'HU river only')
    need(data['result']['context_key'] == identity(context), 'Context mismatch')
    need(type(history) is list, 'Invalid history')
    known = {} if known is None else known
    need(type(known) is dict and set(known) <= set(c['seats']), 'Invalid known holdings')
    known = {p: tuple(cards(h)) for p, h in known.items()}
    hits = [x for x in data['tree'] if x['history'] == history]
    if len(hits) != 1:
        return dict(status='UNMODELED_HISTORY', deals=[])
    by_history = {len(x['history']): x for x in data['tree'] if x['history'] == history[:len(x['history'])]}
    policy = {(r['node'], tuple(r['holding'])): r for r in data['result']['policy']}
    ranges = [[(tuple(row['cards']), row['weight']) for row in c['ranges'][p]
               if p not in known or tuple(row['cards']) == known[p]] for p in c['seats']]
    need(len(ranges[0])*len(ranges[1]) <= 4096, 'Pair budget exceeded')
    factors = []
    for p, rows in enumerate(ranges):
        fs = {}
        for h, weight in rows:
            f = Fraction(weight)
            for i, event in enumerate(history):
                if event['position'] != c['seats'][p]:
                    continue
                row = policy.get((by_history[i]['node'], h))
                if row is None:
                    f = None
                    break
                aa = [a for a in row['actions'] if (a['action'], a['amount']) == (event['action'], event['amount'])]
                if len(aa) != 1:
                    f = None
                    break
                v = aa[0]['frequency']
                need(type(v) in (int, float) and isfinite(v) and 0 <= v <= 1, 'Invalid frequency')
                f *= Fraction(str(v))
            fs[h] = f
        factors.append(fs)
    deals = []
    prior = 0
    for a, wa in ranges[0]:
        for b, wb in ranges[1]:
            if set(a) & set(b):
                continue
            prior += wa*wb
            x, y = factors[0][a], factors[1][b]
            if x is None or y is None:
                return dict(status='INCOMPLETE_POLICY', deals=[])
            if x*y:
                deals.append((a, b, x*y))
    if not prior:
        return dict(status='NO_LEGAL_RANGE', deals=[])
    mass = sum((w for _, _, w in deals), Fraction(0))
    if not mass:
        return dict(status='ZERO_ACTION_LIKELIHOOD', deals=[])
    def ratio(f):
        return [f.numerator, f.denominator]
    return dict(status='CONDITIONAL_JOINT_RANGE', node=hits[0]['node'],
                seats=c['seats'], action_probability=ratio(mass/prior),
                deals=[dict(holdings=[list(a), list(b)], exact_probability=ratio(w/mass)) for a,b,w in deals],
                range_assumptions_verified=False, gto_solution=False)


def exact_integer_weights(rows, max_weight=10**12):
    """Adapt rational marginal rows only when exact representation fits schema."""
    need(type(max_weight) is int and 1 <= max_weight <= 10**12, 'Invalid weight budget')
    need(type(rows) is list and 0 < len(rows) <= 4096, 'Invalid posterior rows')
    parsed = []
    seen = set()
    for row in rows:
        h = tuple(cards(row['cards']))
        need(h not in seen, 'Duplicate holding')
        seen.add(h)
        n,d = row['exact_probability']
        need(type(n) is int and type(d) is int and 0 < n <= d and d.bit_length() <= 4096, 'Invalid probability')
        parsed.append((h, Fraction(n,d)))
    need(sum((f for _,f in parsed), Fraction(0)) == 1, 'Posterior not normalized')
    den = 1
    for _,f in parsed:
        den = lcm(den, f.denominator)
        # For normalized probabilities, minimal integer weights sum to this LCM.
        if den > len(parsed)*max_weight:
            return dict(status='EXACT_WEIGHT_BUDGET_EXCEEDED', rows=[])
    weights = [int(f*den) for _,f in parsed]
    common = gcd(*weights)
    weights = [w//common for w in weights]
    if max(weights) > max_weight:
        return dict(status='EXACT_WEIGHT_BUDGET_EXCEEDED', rows=[])
    return dict(status='EXACT_WEIGHTS', rows=[dict(cards=list(h), weight=w) for (h,_),w in zip(parsed,weights)])
