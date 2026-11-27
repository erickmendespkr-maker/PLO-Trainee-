"""Offline HU observed-history bridge; NOT a complete preflop equilibrium.
Explicit action likelihoods condition a joint prior before an observed flop.
A postflop solve is local to this public branch; never feed its EV into an
unrelated preflop leaf or treat one observed flop as all possible runouts.
"""
from fractions import Fraction
from hashlib import sha256
from itertools import product
from math import comb, gcd, lcm, isfinite
import json
from plo5_pre_gto_context import normalize, identity, cards, need
from plo5_pre_gto_tree import replay
from plo5_post_gto_context import DECK
from plo5_post_gto_multiway import solve

VERSION = 'hu-observed-flop-bridge-v1'


def _hash(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _ratio(q):
    return [q.numerator,q.denominator]


def _likelihood(x):
    need(type(x) in (float,int) and isfinite(x) and 0<=x<=1,'Invalid likelihood')
    return Fraction(str(x))


def _condition(context, likelihoods):
    c=normalize(context)
    need(set(c['stacks'])=={'SB','BB'},'HU only; folded pre-root blockers unsupported')
    state=replay(c['stacks'],c['sb'],c['bb'],c['history'])
    need(state.status=='flop_transition' and len(state.active)==2 and state.paid[0]==state.paid[1],
         'Settled HU flop transition required')
    need(type(likelihoods) is list and len(likelihoods)==len(c['history']),'One likelihood map per observed action required')
    ranges=[[(tuple(x['cards']),x['weight']) for x in c['ranges'][p]] for p in state.order]
    need(len(ranges[0])*len(ranges[1])<=4096,'Pair budget exceeded')
    pairs=[((a,b),Fraction(wa*wb)) for (a,wa),(b,wb) in product(*ranges) if not set(a)&set(b)]
    prior=sum(w for h,w in pairs);need(prior>0,'No legal joint deals')
    maps=[]
    for event,rows in zip(c['history'],likelihoods):
        p=state.order.index(event['position']); allowed={h for h,w in ranges[p]}
        need(type(rows) is list and len(rows)<=len(allowed),'Invalid likelihood rows')
        fs={}
        for row in rows:
            need(type(row) is dict and set(row)=={'cards','frequency'},'Invalid likelihood row')
            h=tuple(cards(row['cards']));need(h in allowed and h not in fs,'Unexpected or duplicate holding')
            fs[h]=_likelihood(row['frequency'])
        need(all(h[p] in fs for h,w in pairs),'INCOMPLETE_POLICY')
        pairs=[(h,w*fs[h[p]]) for h,w in pairs if w*fs[h[p]]]
        need(bool(pairs),'ZERO_ACTION_LIKELIHOOD')
        maps.append([dict(cards=list(h),probability=_ratio(f)) for h,f in sorted(fs.items())])
    mass=sum(w for h,w in pairs)
    return c,state,pairs,mass/prior,maps


def prepare_flop(context, flop, likelihoods, *, approximate_joint=False):
    need(type(approximate_joint) is bool,'Invalid approximation flag')
    c,state,pairs,history_prob,maps=_condition(context,likelihoods)
    need(type(flop) is list and len(flop)==3 and all(type(x) is str and x in DECK for x in flop)
         and len(set(flop))==3,'Invalid flop')
    flop=sorted(flop); dead=set(flop)
    mass=sum(w for h,w in pairs)
    legal=[(h,w) for h,w in pairs if not dead.intersection(h[0]+h[1])]
    need(bool(legal),'ZERO_FLOP_LIKELIHOOD')
    survive=sum(w for h,w in legal)
    # Each legal physical pair has C(42,3) equiprobable unordered flops.
    flop_prob=survive/(mass*comb(42,3))
    normalized=[(h,w/survive) for h,w in legal]
    den=1; exact=True
    for h,p in normalized:
        den=lcm(den,p.denominator)
        if den>len(normalized)*10**12:
            exact=False;break
    if exact:
        weights=[int(p*den) for h,p in normalized];div=gcd(*weights)
        weights=[w//div for w in weights]
        exact=max(weights)<=10**12
    if not exact:
        need(approximate_joint,'EXACT_WEIGHT_BUDGET_EXCEEDED')
        # Reserve one unit for each positive holding pair; distribute remaining
        # units by largest remainders, preserving support deterministically.
        budget=10**12;left=budget-len(normalized)
        quotas=[p*left for h,p in normalized];floors=[int(q) for q in quotas]
        weights=[1+x for x in floors]
        missing=budget-sum(weights)
        order=sorted(range(len(weights)),key=lambda i:(-(quotas[i]-floors[i]),i))
        for i in order[:missing]:weights[i]+=1
    total=sum(weights)
    tv=sum(abs(Fraction(w,total)-p) for w,(h,p) in zip(weights,normalized))/2
    need(tv<=Fraction(1,10**6),'APPROXIMATION_ERROR_EXCEEDED')
    # HU button/SB acts last postflop. Reorder from preflop SB,BB to BB,SB.
    seats=['BB','SB'];order=[state.order.index(p) for p in seats]
    joint=[dict(holdings=[list(h[i]) for i in order],weight=w) for (h,p),w in zip(normalized,weights)]
    rr={p:[dict(cards=list(h),weight=1) for h in sorted({tuple(x['holdings'][i]) for x in joint})]
        for i,p in enumerate(seats)}
    post=dict(variant=5,board=flop,seats=seats,actor='BB',pot=state.pot,bb=c['bb'],
              stacks={p:state.remaining[i] for p,i in zip(seats,order)},ranges=rr,
              rake_bps=c['rake_bps'],rake_cap=c['rake_cap'],tree_version='post-gto-tree-v1',continuation_version=VERSION)
    info=dict(version=VERSION,preflop_context_key=identity(context)['key'],likelihood_sha256=_hash(maps),
              history_probability=_ratio(history_prob),flop_given_history_probability=_ratio(flop_prob),
              preflop_paid_chips=dict(zip(state.order,state.paid)),rake_on_fold=c['rake_on_fold'],
              post_context=post,joint=joint,joint_weights_exact=exact,joint_weight_tv=_ratio(tv),scope='observed_flop_conditional_reach',
              likelihoods_model_verified=False,preflop_continuation_certified=False)
    return dict(info,bridge_key=_hash(info))


def solve_observed_flop(context, flop, likelihoods, *, approximate_joint=False, **kwargs):
    b=prepare_flop(context,flop,likelihoods,approximate_joint=approximate_joint)
    r=solve(b['post_context'],joint=b['joint'],rake_on_fold=b['rake_on_fold'],include_deal_values=True,**kwargs)
    seats=r['seats'];bb=b['post_context']['bb'];paid=b['preflop_paid_chips']
    # Whole-hand net utility: subtract preflop paid once, from root-pot-inclusive EV.
    def net(v):return [x-paid[p]/bb for p,x in zip(seats,v)]
    rows=[dict(x,net_from_hand_start_bb=net(x['values_bb'])) for x in r['conditional_values']['rows']]
    return dict(bridge=b,postflop=r,seats=seats,net_from_hand_start_bb=net(r['values_bb']),
                conditional_net_rows=rows,preflop_continuation_certified=False,
                scope='one_observed_public_flop_and_explicit_action_model')
