"""PLO5 preflop joint range equity, offline, 2-6 seats.
Independent weighted physical holdings conditioned jointly on disjointness.
Rejection sampling avoids the bias of sequential blocker renormalization.
Uniform ranges are implicit. Equal eligible pot; no side pots or strategy.
"""
from bisect import bisect_right
from itertools import accumulate
from math import log, sqrt
import random
from plo5_pre_gto_context import cards, need
from plo5_evaluator import evaluate

DECK=tuple(r+s for r in "23456789TJQKA" for s in "cdhs")
VERSION="preflop-joint-equity-v1"

def sampler(spec):
    if spec=={"kind":"uniform"}:
        return lambda rng: tuple(rng.sample(DECK,5))
    need(type(spec) is dict and set(spec)=={"kind","holdings"} and
         spec["kind"]=="weighted_holdings","Invalid range specification")
    rows=spec["holdings"]
    need(type(rows) is list and 1<=len(rows)<=2598960,"Invalid range size")
    seen=set(); hands=[]; weights=[]
    for row in rows:
        need(type(row) is dict and set(row)=={"cards","weight"},"Invalid holding")
        h=tuple(cards(row["cards"]));w=row["weight"]
        need(h not in seen and type(w) is int and 1<=w<=10**12,"Duplicate or invalid weight")
        seen.add(h);hands.append(h);weights.append(w)
    ordered=sorted(zip(hands,weights))
    hands=[h for h,w in ordered];ends=list(accumulate(w for h,w in ordered))
    return lambda rng: hands[bisect_right(ends,rng.randrange(ends[-1]))]

def equity(ranges, *, trials=10000, seed=42, max_attempts=1000000, dead=()):
    need(type(ranges) in (list,tuple) and 2<=len(ranges)<=6,"Expected 2-6 ranges")
    need(type(trials) is int and 1<=trials<=1000000 and
         type(max_attempts) is int and trials<=max_attempts<=100000000 and
         type(seed) is int and 0<=seed<2**64,"Invalid budget or seed")
    need(type(dead) in (tuple,list) and all(type(c) is str and c in DECK for c in dead)
         and len(set(dead))==len(dead) and len(dead)+5*len(ranges)+5<=52,"Invalid dead cards")
    draws=[None if s=={"kind":"uniform"} else sampler(s) for s in ranges]
    rng=random.Random(seed);n=len(draws)
    # 60 is divisible by every possible winner count (1-6).
    units=[0]*n;wins=[0]*n;ties=[0]*n;accepted=attempts=0
    blocked=set(dead)
    while accepted<trials and attempts<max_attempts:
        attempts+=1
        hands=[draw(rng) if draw is not None else None for draw in draws]
        explicit=[h for h in hands if h is not None]
        used=blocked.union(*explicit)
        if len(used)!=len(blocked)+5*len(explicit):continue
        for i,h in enumerate(hands):
            if h is None:
                hands[i]=tuple(rng.sample([c for c in DECK if c not in used],5))
                used.update(hands[i])
        board=rng.sample([c for c in DECK if c not in used],5)
        ranks=[evaluate(h,board)["rank"] for h in hands]
        best=max(ranks);winners=[i for i,r in enumerate(ranks) if r==best]
        for i in winners:
            units[i]+=60//len(winners)
            if len(winners)==1:wins[i]+=1
            else:ties[i]+=1
        accepted+=1
    # Never publish incomplete simulations as successful results.
    need(accepted==trials,"Joint range sampling budget exhausted; insufficient legal draws")
    assert sum(units)==60*accepted
    radius=sqrt(log(2*n/.05)/(2*accepted))
    shares=[u/(60*accepted) for u in units]
    return dict(version=VERSION,variant=5,trials=accepted,attempts=attempts,
                acceptance_rate=accepted/attempts,seed=seed,share_units=units,
                share_denominator=60*accepted,equity=shares,wins=wins,ties=ties,
                simultaneous_ci95=[[max(0,q-radius),min(1,q+radius)] for q in shares],
                conditioning="joint_disjoint_product_weights",gto_solution=False,
                future_betting_modeled=False,rake_modeled=False,side_pots_modeled=False)

def selftest():
    a={"kind":"weighted_holdings","holdings":[{"cards":["As","Kd","Qh","Jc","Ts"],"weight":1}]}
    b={"kind":"weighted_holdings","holdings":[{"cards":["2s","3d","4h","5c","6s"],"weight":1}]}
    r=equity([a,b],trials=100,seed=7)
    assert sum(r["share_units"])==6000 and r["attempts"]==100
    assert r==equity([a,b],trials=100,seed=7)
    r=equity([{"kind":"uniform"}]*6,trials=20,seed=7,max_attempts=100000)
    assert sum(r["share_units"])==1200
    try:equity([a,a],trials=2,max_attempts=10)
    except ValueError:pass
    else:raise AssertionError("Overlapping fixed holdings accepted")
    print("Joint equity checks passed")

if __name__=="__main__":
    selftest()
