"""Independent exact chip-layer oracle for multiway settlement."""
from fractions import Fraction
from random import Random
from types import SimpleNamespace
from plo5_pre_gto_multiway import settlement

def oracle(paid,folded,ranks,cfg):
    active=[i for i,f in enumerate(folded) if not f]
    layers=[[i for i,p in enumerate(paid) if p>=j] for j in range(1,max(paid)+1)]
    fee=min(cfg["cap"],sum(len(x) for x in layers if len(x)>1)*cfg["bps"]//10000)
    if len(active)==1 and not cfg["on_fold"]:fee=0
    out=[Fraction(-x) for x in paid]
    for layer in layers:
        if len(layer)==1:
            out[layer[0]]+=1;continue
        eligible=[i for i in layer if i in active]
        if len(active)==1:eligible=active
        winners=[i for i in eligible if ranks[i]==max(ranks[j] for j in eligible)]
        take=min(fee,len(layer));fee-=take
        for i in winners:out[i]+=Fraction(len(layer)-take,len(winners))
    return out

def run():
    rng=Random(42);count=0
    for n in range(2,7):
        for _ in range(2000):
            paid=[rng.randrange(1,51) for i in range(n)]
            top=paid.index(max(paid))
            folded=[bool(rng.randrange(2)) for i in range(n)]
            folded[top]=False
            active=[i for i,f in enumerate(folded) if not f]
            ranks=[rng.randrange(5) for i in range(n)]
            cfg=dict(bps=rng.choice([0,500,1000,10000]),cap=rng.randrange(21),on_fold=bool(rng.randrange(2)))
            s=SimpleNamespace(paid=paid,active=active,folded=folded,pending=())
            a=settlement(s,ranks,cfg);b=oracle(paid,folded,ranks,cfg)
            assert all(abs(x-float(y))<1e-9 for x,y in zip(a,b)),(s,a,b,cfg)
            count+=1
    print("PASS",count,"settlements against exact Fraction chip-layer oracle")
    return count

if __name__=="__main__":run()
