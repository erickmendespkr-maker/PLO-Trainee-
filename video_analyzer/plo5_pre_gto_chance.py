"""Offline PLO5 multiway chance sampling from independent weighted ranges,
conditioned jointly on card disjointness. Finite support, not full-game GTO.
"""
import random
from collections import Counter
from plo5_pre_gto_context import need
from plo5_pre_gto_equity import DECK,sampler

def sample_ranges(ranges,*,trials=512,seed=42,max_attempts=100000):
    need(type(ranges) in (list,tuple) and 2<=len(ranges)<=6,"Expected 2-6 seats")
    need(type(trials) is int and 1<=trials<=2048,"Invalid trial budget")
    need(type(max_attempts) is int and trials<=max_attempts<=10000000,"Invalid attempt budget")
    need(type(seed) is int and 0<=seed<2**64,"Invalid seed")
    draws=[None if s=={"kind":"uniform"} else sampler(s) for s in ranges]
    rng=random.Random(seed); deals=Counter();attempts=accepted=0
    while accepted<trials and attempts<max_attempts:
        attempts+=1
        hands=[tuple(sorted(draw(rng))) if draw else None for draw in draws]
        explicit=[h for h in hands if h is not None]
        used=set().union(*explicit)
        if len(used)!=5*len(explicit):continue
        for i,h in enumerate(hands):
            if h is None:
                hands[i]=tuple(sorted(rng.sample([c for c in DECK if c not in used],5)))
                used.update(hands[i])
        board=tuple(sorted(rng.sample([c for c in DECK if c not in used],5)))
        deals[tuple(hands),board]+=1
        accepted+=1
    need(accepted==trials,"Joint sampling budget exhausted")
    rows=[dict(hands=[list(h) for h in hands],board=list(board),weight=w) for (hands,board),w in sorted(deals.items())]
    counts=[Counter() for _ in ranges]
    for row in rows:
        for i,h in enumerate(row["hands"]):counts[i][tuple(h)]+=row["weight"]
    return dict(deals=rows,attempts=attempts,accepted=accepted,acceptance_rate=accepted/attempts,
                seat_unique_holdings=[len(c) for c in counts],
                seat_singleton_mass=[sum(v for v in c.values() if v==1)/accepted for c in counts],
                conditioning="joint_disjoint_product_weights",gto_solution=False)

def selftest():
    r=sample_ranges([{"kind":"uniform"}]*6,trials=100,seed=7)
    assert r==sample_ranges([{"kind":"uniform"}]*6,trials=100,seed=7)
    assert sum(d["weight"] for d in r["deals"])==100
    for d in r["deals"]:
        assert len(set(d["board"]).union(*d["hands"]))==35
    a={"kind":"weighted_holdings","holdings":[{"cards":["As","Ks","Qh","Jd","Tc"],"weight":1}]}
    try:sample_ranges([a,a],trials=2,max_attempts=10)
    except ValueError:pass
    else:raise AssertionError("Overlapping ranges accepted")
    print("PASS multiway chance sampling")
if __name__=="__main__":selftest()
