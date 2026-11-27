"""Independent normal-form best-response audit for tiny HU preflop games.
Enumerates pure deviations rather than using CFR's recursive best response.
Synthetic equity inputs only; bounded exponential reference, not production solver.
"""
from itertools import product
from math import prod, isfinite
from plo5_pre_gto_tree import start, step
from plo5_pre_gto_hu import solve

def audit(report,stacks,sb,bb,pairs,*,limit=20000):
    nodes={x["node"]:x for x in report["tree"]}
    policy={(x["node"],x["holding"]):x for x in report["policy"]}
    mass=sum(w for i,j,w,q in pairs)
    states={}
    def replay(n,s):
        assert n not in states
        states[n]=s
        t=nodes[n]
        assert t["position"]==s.actor and t["paid"]==list(s.paid) and t["status"]==s.status
        if s.pending:
            rows=[x for (k,h),x in policy.items() if k==n]
            assert rows
            sig=[(a["action"],a["amount"]) for a in rows[0]["actions"]]
            assert len(sig)==len(t["children"])
            for row in rows:
                assert [(a["action"],a["amount"]) for a in row["actions"]]==sig
                f=[a["frequency"] for a in row["actions"]]
                assert all(isfinite(x) and 0<=x<=1 for x in f) and abs(sum(f)-1)<1e-8
            for (a,b),c in zip(sig,t["children"]):replay(c,step(s,s.actor,a,b))
        else:assert not t["children"]
    replay(0,start(stacks,sb,bb))
    assert len(states)==len(nodes)
    def value(deviation=None,player=None):
        def walk(n,h,q):
            s=states[n]
            if not s.pending:
                a,b=s.paid
                # Direct net payout accounting, including uncalled excess.
                payout=0 if s.folded[0] else a+b if s.folded[1] else max(a-b,0)+2*min(a,b)*q
                return (payout-a)/bb
            actor=s.pending[0];key=(n,h[actor]);ch=nodes[n]["children"]
            if actor==player:return walk(ch[deviation[key]],h,q)
            return sum(a["frequency"]*walk(c,h,q) for a,c in zip(policy[key]["actions"],ch))
        return sum(w*walk(0,(i,j),q)/mass for i,j,w,q in pairs)
    v=value();bounds=[];counts=[]
    for player in (0,1):
        keys=sorted(k for k in policy if states[k[0]].pending[0]==player)
        sizes=[len(policy[k]["actions"]) for k in keys]
        count=prod(sizes)
        if count>limit:raise ValueError("Pure strategy enumeration budget exceeded")
        vals=(value(dict(zip(keys,p)),player) for p in product(*(range(s) for s in sizes)))
        bounds.append((max if player==0 else min)(vals));counts.append(count)
    hi,lo=bounds
    assert abs(v-report["value_sb_bb"])<1e-8
    assert abs(lo-report["best_response_lower_bb"])<1e-8
    assert abs(hi-report["best_response_upper_bb"])<1e-8
    return dict(value_bb=v,lower_bb=lo,upper_bb=hi,nash_gap_bb=hi-lo,pure_strategy_counts=counts)

def selftest():
    for stacks,pairs in [
        ({"SB":2,"BB":2},[(0,0,1,.1),(1,0,3,.8)]),
        ({"SB":4,"BB":4},[(0,0,1,.3),(1,0,2,.7)]),
        ({"SB":5,"BB":4},[(0,0,1,.5)]),
    ]:
        r=solve(stacks,1,2,pairs,iterations=200)
        print(audit(r,stacks,1,2,pairs))
    print("PASS independent normal-form audit")

if __name__=="__main__":selftest()
