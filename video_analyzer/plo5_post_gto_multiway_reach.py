"""Condition explicit multiway joint priors on modeled actions/public draws.
Folded holdings stay in the joint distribution as physical blockers.
"""
from fractions import Fraction
from math import isfinite
from plo5_pre_gto_context import need, cards
from plo5_post_gto_context import normalize
from plo5_post_gto_multiway import prior, model_identity


def condition_path(context,result,history,*,joint=None,known=None):
    c=normalize(context);seats=c['seats'];n=len(seats)
    rows=prior(context,joint)
    need(result['model_key']==model_identity(context,rows,result['rake_on_fold'],result['pot_bps']),'Model mismatch')
    need(type(history) is list and all(type(e) in (list,tuple) and len(e)==3 for e in history),'Invalid history')
    path=tuple(tuple(e) for e in history)
    paths={tuple(tuple(e) for e in row['history']):row for row in result['tree']}
    if path not in paths:return dict(status='UNMODELED_HISTORY',deals=[])
    known={} if known is None else known
    need(type(known) is dict and set(known)<=set(seats),'Invalid known holdings')
    known={seats.index(p):tuple(cards(h)) for p,h in known.items()}
    rows=[(h,Fraction(w)) for h,w in rows if all(h[p]==k for p,k in known.items())]
    initial=sum(w for h,w in rows)
    if not initial:return dict(status='NO_LEGAL_RANGE',deals=[])
    policies={(r['node'],tuple(r['holding'])):r for r in result['policy']}
    for i,(seat,action,amount) in enumerate(path):
        node=paths[path[:i]];next_rows=[]
        for h,w in rows:
            if seat=='chance':
                # Folded cards are still unavailable for a public draw.
                f=Fraction(0) if any(action in k for k in h) else Fraction(1,52-5*n-len(node['board']))
            else:
                p=seats.index(seat);row=policies.get((node['node'],h[p]))
                if row is None:return dict(status='INCOMPLETE_POLICY',deals=[])
                aa=[a for a in row['actions'] if (a['action'],a['amount'])==(action,amount)]
                if len(aa)!=1:return dict(status='INCOMPLETE_POLICY',deals=[])
                v=aa[0]['frequency'];need(type(v) in (float,int) and isfinite(v) and 0<=v<=1,'Invalid frequency')
                f=Fraction(str(v))
            if w*f:next_rows.append((h,w*f))
        rows=next_rows
        if not rows:return dict(status='ZERO_PATH_LIKELIHOOD',deals=[])
    total=sum(w for h,w in rows)
    def ratio(f):return [f.numerator,f.denominator]
    return dict(status='CONDITIONAL_JOINT_RANGE',seats=seats,node=paths[path]['node'],board=paths[path]['board'],
                path_probability=ratio(total/initial),deals=[dict(holdings=[list(k) for k in h],exact_probability=ratio(w/total)) for h,w in rows],
                folded_cards_retained=True,range_assumptions_verified=False,gto_solution=False)
