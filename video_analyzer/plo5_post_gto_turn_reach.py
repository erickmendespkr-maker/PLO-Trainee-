"""Offline conditional joint turn/river ranges from observed public history."""
from fractions import Fraction
from math import isfinite
from plo5_post_gto_context import normalize, identity
from plo5_pre_gto_context import cards, need


def condition_path(context,result,history,known=None):
    c=normalize(context)
    need(len(c['seats'])==2 and len(c['board'])==4,'HU turn only')
    need(result['context_key']==identity(context),'Context mismatch')
    need(type(history) is list,'Invalid history')
    known={} if known is None else known
    need(type(known) is dict and set(known)<=set(c['seats']),'Invalid known holdings')
    known={p:tuple(cards(h)) for p,h in known.items()}
    paths={tuple(tuple(e) for e in row['history']):row for row in result['tree']}
    need(all(type(e) in (list,tuple) and len(e)==3 for e in history),'Invalid history entry')
    path=tuple(tuple(e) for e in history)
    if path not in paths:return dict(status='UNMODELED_HISTORY',deals=[])
    rows=[[(tuple(r['cards']),r['weight']) for r in c['ranges'][p] if p not in known or tuple(r['cards'])==known[p]] for p in c['seats']]
    need(len(rows[0])*len(rows[1])<=4096,'Pair budget exceeded')
    pairs=[(h,k,Fraction(w*v)) for h,w in rows[0] for k,v in rows[1] if not set(h)&set(k)]
    prior=sum(w for _,_,w in pairs)
    if not prior:return dict(status='NO_LEGAL_RANGE',deals=[])
    policy={(r['node'],tuple(r['holding'])):r for r in result['policy']}
    for idx,(position,action,amount) in enumerate(path):
        node=paths[path[:idx]]['node']; next_pairs=[]
        for h,k,w in pairs:
            if position=='chance':
                # One public draw conditional on the physical deal. Never apply future cards early.
                factor=Fraction(0) if action in h or action in k else Fraction(1,38)
            else:
                p=c['seats'].index(position)
                row=policy.get((node,(h,k)[p]))
                if row is None:return dict(status='INCOMPLETE_POLICY',deals=[])
                aa=[a for a in row['actions'] if (a['action'],a['amount'])==(action,amount)]
                if len(aa)!=1:return dict(status='INCOMPLETE_POLICY',deals=[])
                v=aa[0]['frequency'];need(type(v) in (int,float) and isfinite(v) and 0<=v<=1,'Invalid frequency')
                factor=Fraction(str(v))
            if w*factor:next_pairs.append((h,k,w*factor))
        pairs=next_pairs
        if not pairs:return dict(status='ZERO_PATH_LIKELIHOOD',deals=[])
    mass=sum(w for _,_,w in pairs)
    def ratio(x):return [x.numerator,x.denominator]
    return dict(status='CONDITIONAL_JOINT_RANGE',node=paths[path]['node'],board=paths[path]['board'],
                path_probability=ratio(mass/prior),deals=[dict(holdings=[list(h),list(k)],exact_probability=ratio(w/mass)) for h,k,w in pairs],
                range_assumptions_verified=False,gto_solution=False)
