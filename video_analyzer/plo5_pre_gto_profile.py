"""Explicit restricted sizing profile, independently configurable stack depth.
No pruning of legal fold/call/check; omitted raises remain unmodeled.
"""
from plo5_pre_gto_context import ORDERS,need,integer
from plo5_pre_gto_tree import bounds,start,step
from collections import Counter

VERSION="pre-gto-sizing-profile-v1"
DEFAULT={"open_bps":[10000],"reraise_bps":[10000],"include_min":False}

def profile_actions(state,raise_count,profile):
    need(type(profile) is dict and set(profile)==set(DEFAULT),"Invalid profile")
    need(type(profile["include_min"]) is bool,"Invalid minimum flag")
    for key in ("open_bps","reraise_bps"):
        vals=profile[key]
        need(type(vals) is list and 1<=len(vals)<=8 and all(type(v) is int and 1<=v<=10000 for v in vals),"Invalid pot fractions")
    b=bounds(state);c=b["to_call"]
    out=[("fold",0),("call",b["call_payment"])] if c else [("check",0)]
    lo,hi=b["raise_min"],b["raise_max"]
    if lo is not None:
        sizes={hi}
        if profile["include_min"]:sizes.add(lo)
        for f in profile["open_bps" if raise_count==0 else "reraise_bps"]:
            x=c+(b["pot"]+c)*f//10000
            if lo<=x<=hi:sizes.add(x)
        out.extend(("raise",x) for x in sorted(sizes))
    return tuple(out)

def census(stacks,sb,bb,profile=None,*,node_limit=100000):
    profile=DEFAULT if profile is None else profile
    integer(node_limit,1);need(node_limit<=1000000,"Census limit")
    pending=[(start(stacks,sb,bb),0,0)]
    counts=Counter();max_depth=0;total=0
    while pending and total<node_limit:
        s,r,d=pending.pop();total+=1;counts[s.status]+=1;max_depth=max(max_depth,d)
        if s.pending:
            for a,x in profile_actions(s,r,profile):
                pending.append((step(s,s.actor,a,x),r+(a=="raise"),d+1))
    return dict(version=VERSION,nodes_visited=total,unvisited_frontier=len(pending),
                complete=not pending,status_counts=dict(counts),max_depth=max_depth,
                stack_chips=dict(stacks),bb=bb,profile=profile,gto_solution=False)

def stacks_at_depth(players,bb=2,depth_bb=100):
    need(type(players) is int and players in ORDERS,"Invalid seats")
    integer(bb,2);integer(depth_bb,1)
    return {p:bb*depth_bb for p in ORDERS[players]}

def selftest():
    s=start(stacks_at_depth(6),1,2)
    assert profile_actions(s,0,DEFAULT)==(("fold",0),("call",2),("raise",7))
    s=step(s,"UTG","raise",7)
    assert profile_actions(s,1,DEFAULT)==(("fold",0),("call",7),("raise",24))
    r=census(stacks_at_depth(2),1,2,node_limit=10000)
    assert r["complete"] and r["nodes_visited"]>1
    print(r)
if __name__=="__main__":selftest()
