"""Deterministic randomized invariant audit for the preflop betting tree."""
import random
from plo5_pre_gto_tree import start, actions, step, bounds
from plo5_pre_gto_context import ORDERS

def run(seed=42):
    rng=random.Random(seed);count=0
    for n in range(2,7):
        for _ in range(2000):
            s=start({p:rng.randrange(2,401) for p in ORDERS[n]},1,2)
            while s.pending:
                assert len(set(s.pending))==len(s.pending)
                assert all(i in s.active and s.remaining[i]>0 for i in s.pending)
                a,x=rng.choice(actions(s));t=step(s,s.actor,a,x)
                assert t.pot==s.pot+x and min(t.remaining)>=0
                count+=1;s=t
            if len(s.active)>1:
                assert all(s.remaining[i]==0 or s.paid[i]==max(s.paid[j] for j in s.active) for i in s.active) or sum(s.remaining[i]>0 for i in s.active)<=1
    s=start({"CO":100,"BTN":9,"SB":11,"BB":100},1,2)
    for p,a,x in [("CO","raise",7),("BTN","raise",9),("SB","raise",10),("BB","call",9)]:
        s=step(s,p,a,x)
    assert not bounds(s)["reopened"]
    print("PASS 10000 random hands",count,"transitions and short raise non-reopening")
    return count
if __name__=="__main__":run()
