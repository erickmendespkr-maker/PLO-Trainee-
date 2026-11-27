"""Offline reproducible PLO5 HU equity estimates for explicitly declared ranges."""
import argparse, json, random, math
from itertools import combinations
from bisect import bisect_right
from offline_omaha_showdown import _cards, RANKS
from plo5_exact_river_equity import DECK
from plo5_rank_cache import fast_five


def make_range(pool, spec):
    """Uniform holdings, exact rank-count filter, or explicit integer-weighted holdings.

    Conditioning excludes known blockers before sampling. Weights are per physical
    holding, not per descriptor. Rank-count ranges are uniform within the filter.
    """
    if type(spec) is not dict:raise ValueError('Invalid range')
    kind=spec.get('kind');available=set(pool)
    if kind=='uniform' and set(spec)=={'kind'}:
        return lambda rng:tuple(rng.sample(pool,5)),math.comb(len(pool),5),0
    if kind=='rank_count' and set(spec)=={'kind','rank','min','max'}:
        r,lo,hi=spec['rank'],spec['min'],spec['max']
        if type(r) is not str or len(r)!=1 or r not in RANKS or type(lo) is not int or type(hi) is not int or not 0<=lo<=hi<=4:raise ValueError('Invalid rank count')
        a=tuple(c for c in pool if c[0]==r);b=tuple(c for c in pool if c[0]!=r);ks=[];ends=[];total=0
        for k in range(lo,hi+1):
            if k<=len(a) and 5-k<=len(b):
                total+=math.comb(len(a),k)*math.comb(len(b),5-k);ks.append(k);ends.append(total)
        if not total:raise ValueError('Range empty after blockers')
        def draw(rng):
            k=ks[bisect_right(ends,rng.randrange(total))];return tuple(rng.sample(a,k)+rng.sample(b,5-k))
        return draw,total,0
    if kind=='weighted_holdings' and set(spec)=={'kind','holdings'}:
        rows=spec['holdings']
        if type(rows) is not list or not 1<=len(rows)<=100000:raise ValueError('Invalid holdings count')
        hands=[];ends=[];total=blocked=0;seen=set()
        for row in rows:
            if type(row) is not dict or set(row)!={'cards','weight'} or type(row['weight']) is not int or not 1<=row['weight']<=10**9:raise ValueError('Invalid weighted holding')
            h=tuple(sorted(_cards(row['cards'],5)))
            if h in seen:raise ValueError('Duplicate holding')
            seen.add(h)
            if not set(h)<=available:blocked+=1;continue
            hands.append(h);total+=row['weight'];ends.append(total)
        if not total:raise ValueError('Range empty after blockers')
        return lambda rng:hands[bisect_right(ends,rng.randrange(total))],len(hands),blocked
    raise ValueError('Unsupported range specification')


def estimate(hero,board,spec,*,trials=10000,seed=42,dead=()):
    h=_cards(hero,5)
    if not isinstance(board,(list,tuple)) or len(board) not in (0,3,4,5):raise ValueError('Invalid board length')
    b=_cards(board,len(board))
    if not isinstance(dead,(list,tuple)) or len(dead)>37:raise ValueError('Invalid dead cards')
    d=_cards(dead,len(dead));known=set(h+b+d)
    if len(known)!=len(h+b+d):raise ValueError('Overlapping known cards')
    pool=tuple(c for c in DECK if c not in known)
    missing=5-len(b)
    if len(pool)<5+missing:raise ValueError('Insufficient unseen cards')
    if type(trials) is not int or not 100<=trials<=100000 or type(seed) is not int or not 0<=seed<2**64:raise ValueError('Invalid simulation budget or seed')
    draw,support,blocked=make_range(pool,spec);rng=random.Random(seed);hp=tuple(combinations(h,2));w=t=l=0
    for _ in range(trials):
        o=draw(rng);excluded=set(o);runout=tuple(rng.sample([c for c in pool if c not in excluded],missing));triples=tuple(combinations(b+runout,3))
        hr=max(fast_five(p+q) for p in hp for q in triples);vr=max(fast_five(p+q) for p in combinations(o,2) for q in triples)
        if hr>vr:w+=1
        elif hr==vr:t+=1
        else:l+=1
    e=(w+t/2)/trials;radius=math.sqrt(math.log(40)/(2*trials))
    return {'variant':5,'method':'fixed_budget_hu_monte_carlo','range_kind':spec['kind'],'legal_range_holdings':support,'blocked_explicit_holdings':blocked,'hero':list(h),'board':list(b),'declared_dead':list(d),'trials':trials,'seed':seed,'wins':w,'ties':t,'losses':l,'equity':e,'hoeffding_95_interval':[max(0.,e-radius),min(1.,e+radius)],'gto_solution':False,'range_inferred':False,'video_verified':False,'financial_result_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hero',nargs=5,required=True);p.add_argument('--board',nargs='*',default=[]);p.add_argument('--range-json',required=True);p.add_argument('--trials',type=int,default=10000);p.add_argument('--seed',type=int,default=42);p.add_argument('--dead',nargs='*',default=[]);a=p.parse_args(argv)
    print(json.dumps(estimate(a.hero,a.board,json.loads(a.range_json),trials=a.trials,seed=a.seed,dead=a.dead),indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
