"""Exact terminal chip layers for 2–6 seats; base pot assumes equal eligibility.
No prior side pots, room-specific odd chips or strategy training.
"""
from fractions import Fraction
from plo5_pre_gto_context import need, integer


def settle(base_pot, contributions, folded, ranks, rake_bps=0, rake_cap=0, *, rake_on_fold):
    integer(base_pot);integer(rake_cap)
    need(integer(rake_bps)<=10000 and type(rake_on_fold) is bool,'Invalid rake rule')
    need(type(contributions) in (list,tuple) and 2<=len(contributions)<=6,'Invalid seats')
    n=len(contributions);paid=tuple(integer(x) for x in contributions)
    need(type(folded) in (list,tuple) and len(folded)==n and all(type(f) is bool for f in folded),'Invalid folds')
    need(type(ranks) in (list,tuple) and len(ranks)==n,'Invalid ranks')
    active=[i for i in range(n) if not folded[i]];need(bool(active),'No eligible seat')
    if len(active)>1:need(all(type(ranks[i]) is tuple and bool(ranks[i]) and all(type(x) is int for x in ranks[i]) for i in active),'Missing showdown rank')
    layers=[(base_pot,active)] if base_pot else []; returned=[0]*n;previous=0
    for level in sorted(set(paid)-{0}):
        contributors=[i for i in range(n) if paid[i]>=level];amount=(level-previous)*len(contributors);previous=level
        if len(contributors)==1:
            i=contributors[0];need(not folded[i],'Folded uncalled excess');returned[i]+=amount;continue
        eligible=[i for i in contributors if not folded[i]];need(bool(eligible),'No eligible seat for contribution layer')
        layers.append((amount,eligible))
    contested=sum(a for a,_ in layers)
    fee=min(rake_cap,contested*rake_bps//10000) if len(active)>1 or rake_on_fold else 0
    # Explicit modeling assumption: allocate fee proportionally across pots,
    # retain fractional chips; do not claim actual room settlement rules.
    awards=[Fraction(0)]*n;out=[]
    for amount,eligible in layers:
        layer_fee=Fraction(fee*amount,contested)
        winners=eligible if len(eligible)==1 else [i for i in eligible if ranks[i]==max(ranks[j] for j in eligible)]
        share=(amount-layer_fee)/len(winners)
        for i in winners:awards[i]+=share
        out.append(dict(gross=amount,eligible=eligible,winners=winners,rake=layer_fee))
    utility=[awards[i]+returned[i]-paid[i] for i in range(n)]
    need(sum(awards)+sum(returned)+fee==base_pot+sum(paid),'Chip conservation failure')
    need(sum(utility)+fee==base_pot,'Utility conservation failure')
    return dict(layers=out,contested=contested,rake=fee,returned=returned,awards=awards,utility_chips=utility,
                rake_allocation='proportional_fractional',room_rules_verified=False,gto_solution=False)
