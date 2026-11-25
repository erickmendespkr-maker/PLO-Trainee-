"""Independent exhaustive rank-signature audit and deterministic PLO5 checks.
No external solver, equity database, or GTO assertions.
"""
from collections import Counter
from itertools import combinations, combinations_with_replacement
from math import comb, prod
import argparse
import json
import random
import time

RANKS='23456789TJQKA'
SUITS='cdhs'
DECK=tuple(r+s for r in RANKS for s in SUITS)
EXPECTED={0:1302540,1:1098240,2:123552,3:54912,4:10200,
          5:5108,6:3744,7:624,8:40}


def oracle(cards):
    """Original rank-count classifier, independent of the cached evaluator."""
    values=sorted((RANKS.index(c[0])+2 for c in cards),reverse=True)
    counts={r:values.count(r) for r in set(values)}
    shape=tuple(sorted(counts.values(),reverse=True))
    by_count=sorted(counts,key=lambda r:(counts[r],r),reverse=True)
    flush=len({c[1] for c in cards})==1
    straight=0
    if shape==(1,1,1,1,1):
        if values==[14,5,4,3,2]:straight=5
        elif values[0]-values[-1]==4:straight=values[0]
    if straight and flush:return (8,straight)
    if shape==(4,1):return (7,*by_count)
    if shape==(3,2):return (6,*by_count)
    if flush:return (5,*values)
    if straight:return (4,straight)
    category={(3,1,1):3,(2,2,1):2,(2,1,1,1):1,(1,1,1,1,1):0}[shape]
    return (category,*by_count)


def signatures():
    """One legal physical representative per rank multiset and flush state."""
    for ranks in combinations_with_replacement(RANKS,5):
        counts=Counter(ranks)
        if max(counts.values())>4:continue
        mass=prod(comb(4,n) for n in counts.values())
        if len(counts)==5:
            yield tuple(r+'c' for r in ranks),4
            yield tuple(r+s for r,s in zip(ranks,'cdhsc')),mass-4
        else:
            yield tuple(r+s for r,n in counts.items() for s in SUITS[:n]),mass


def audit_signatures(candidate):
    categories=Counter();actual=Counter();seen=set();errors=[];total=0
    for hand,mass in signatures():
        expected=oracle(hand);observed=candidate(hand)
        categories[expected[0]]+=mass;actual[observed[0]]+=mass;seen.add(expected);total+=1
        if expected!=observed:errors.append({'cards':hand,'expected':expected,'actual':observed})
    if total!=7462 or len(seen)!=7462 or dict(categories)!=EXPECTED or sum(categories.values())!=comb(52,5):
        raise ValueError('Independent enumeration coverage mismatch')
    return {'rank_signatures':total,'distinct_ranks':len(seen),'physical_combinations_represented':sum(categories.values()),
            'expected_category_counts':dict(categories),'candidate_category_counts':dict(actual),
            'mismatches':errors,'agreement':not errors}


def audit_omaha(evaluate,showdown,count=1024,seed=20261125):
    if type(count) is not int or not 1<=count<=4096:raise ValueError('Invalid case count')
    rng=random.Random(seed);errors=[];players=0;street_checks=0;ties=0
    for i in range(count):
        n=2+i%5;cards=rng.sample(DECK,5+5*n);board=cards[:5]
        hands=[cards[5+5*j:10+5*j] for j in range(n)];ranks=[]
        for h in hands:
            for length in (3,4,5):
                b=board[:length]
                rank=max(oracle(a+c) for a in combinations(h,2) for c in combinations(b,3))
                result=evaluate(h,b);street_checks+=1
                if result['rank']!=rank or result['combinations_evaluated']!=10*comb(length,3):
                    errors.append({'case':i,'street':length,'cards':h,'expected':rank,'observed':result['rank']})
            ranks.append(rank)
        expected=[j for j,r in enumerate(ranks) if r==max(ranks)]
        result=showdown(hands,board);players+=n;ties+=len(expected)>1
        shares=[{'numerator':1,'denominator':len(expected)} if j in expected else {'numerator':0,'denominator':1} for j in range(n)]
        if result['winner_indices']!=expected or result['shares']!=shares:
            errors.append({'case':i,'expected_winners':expected,'actual_winners':result['winner_indices']})
    return {'showdowns':count,'holdings':players,'street_checks':street_checks,'ties':ties,'seed':seed,'mismatches':errors,'agreement':not errors}


def main(argv=None):
    from plo5_rank_cache import fast_five
    from plo5_evaluator import evaluate,showdown
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cases',type=int,default=1024);a=p.parse_args(argv)
    start=time.perf_counter();ranks=audit_signatures(fast_five);mid=time.perf_counter();omaha=audit_omaha(evaluate,showdown,a.cases)
    result={'variant':5,'rank_audit':ranks,'omaha_audit':omaha,'rank_seconds':mid-start,'omaha_seconds':time.perf_counter()-mid,
            'independent_local_oracle':True,'external_engine_verified':False,'gto_solution':False,'real_video_verified':False}
    print(json.dumps(result,indent=2));return 0 if ranks['agreement'] and omaha['agreement'] else 1


if __name__=='__main__':raise SystemExit(main())
