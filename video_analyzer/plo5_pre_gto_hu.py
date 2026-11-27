"""Restricted HU PLO5 preflop equilibrium with showdown-only continuation.
Full traversal CFR+ on a bounded sizing tree, private physical holdings,
joint product-weight chance conditioned on blockers. Zero rake (zero sum).
Equity matrix is explicit and separately estimated; certificate is conditional.
"""
from collections import defaultdict
from math import isfinite
from plo5_pre_gto_context import cards, need
from plo5_pre_gto_tree import start, actions, step
from plo5_pre_gto_equity import equity

VERSION="pre-gto-hu-cfr-v3"

def prepare(ranges, *, trials=1000, seed=42, pair_limit=256, native=None, threads=2, reuse_symmetry=False):
    need(type(ranges) in (list,tuple) and len(ranges)==2,"HU only")
    need(type(pair_limit) is int and 1<=pair_limit<=4096,"Invalid pair budget")
    need(all(type(r) is list and r for r in ranges),"Explicit ranges required")
    need(len(ranges[0])*len(ranges[1])<=pair_limit,"Pair budget exceeded")
    rows=[]
    for r in ranges:
        seen=set(); a=[]
        for e in r:
            need(type(e) is dict and set(e)=={"cards","weight"},"Invalid range entry")
            h=tuple(cards(e["cards"])); w=e["weight"]
            need(h not in seen and type(w) is int and 1<=w<=10**12,"Invalid holding weight")
            seen.add(h);a.append((h,w))
        rows.append(sorted(a))
    from plo5_pre_gto_pair_symmetry import joint_key, representative, pair_seed as canonical_seed
    cache={}
    pairs=[]
    for i,(h,w) in enumerate(rows[0]):
        for j,(v,z) in enumerate(rows[1]):
            if set(h)&set(v):continue
            key=joint_key(h,v) if reuse_symmetry else (i,j)
            if key not in cache:
                hh=representative(key) if reuse_symmetry else [h,v]
                pair_seed=canonical_seed(key,seed) if reuse_symmetry else seed+i*len(rows[1])+j
                specs=[{"kind":"weighted_holdings","holdings":[{"cards":list(k),"weight":1}]} for k in hh]
                result=(equity(specs,trials=trials,seed=pair_seed,max_attempts=trials) if native is None
                        else native.equity(hh,trials=trials,seed=pair_seed,threads=threads))
                cache[key]=result["equity"][0]
            pairs.append((i,j,w*z,cache[key]))
    need(pairs,"No legal deals")
    return rows,pairs

def solve(stacks,sb,bb,pairs,*,iterations=2000,target=.01,node_limit=2000,
          max_work=20000000,sizings=(),check_every=0):
    need(set(stacks)=={"SB","BB"},"HU only")
    need(type(iterations) is int and 1<=iterations<=50000,"Invalid iterations")
    need(type(check_every) is int and 0<=check_every<=50000,"Invalid convergence interval")
    need(type(node_limit) is int and 1<=node_limit<=10000,"Invalid node limit")
    need(type(max_work) is int and 1<=max_work<=100000000,"Invalid work budget")
    need(type(target) in (int,float) and isfinite(target) and 0<=target<=1,"Invalid target")
    need(type(pairs) in (list,tuple) and 1<=len(pairs)<=4096,"Invalid pairs")
    seen=set()
    for i,j,w,q in pairs:
        need(type(i) is int and type(j) is int and i>=0 and j>=0 and (i,j) not in seen
             and type(w) is int and 1<=w<=10**24 and type(q) in (int,float) and isfinite(q) and 0<=q<=1,"Invalid pair")
        seen.add((i,j))
    mass=sum(w for i,j,w,q in pairs)
    deals=[(i,j,w/mass,q) for i,j,w,q in pairs]
    nodes=[]
    def build(s):
        need(len(nodes)<node_limit,"Tree node budget exceeded")
        n=len(nodes);nodes.append(None)
        if not s.pending:
            nodes[n]=(s,None,())
        else:
            aa=actions(s,sizings)
            children=tuple(build(step(s,s.actor,a,b)) for a,b in aa)
            nodes[n]=(s,aa,children)
        return n
    build(start(stacks,sb,bb))
    checks=(iterations-1)//check_every if check_every else 0
    need(len(nodes)*len(deals)*(iterations+4+3*checks)<=max_work,"Traversal work budget exceeded")
    holdings=tuple({d[p] for d in deals} for p in range(2))
    regrets={}; sums={}
    for n,(s,aa,ch) in enumerate(nodes):
        if aa:
            actor=s.pending[0]
            for h in holdings[actor]:
                regrets[n,h]=[0.]*len(aa);sums[n,h]=[0.]*len(aa)
    def normalize(v):
        total=sum(v)
        return [x/total for x in v] if total else [1/len(v)]*len(v)
    # Cache only two coefficients per terminal; no dense node x deal table.
    coefficients={}
    for n,(s,aa,ch) in enumerate(nodes):
        if aa is None:
            a,b=s.paid
            coefficients[n]=(-a/bb,0.) if s.folded[0] else (b/bb,0.) if s.folded[1] else (-min(a,b)/bb,2*min(a,b)/bb)
    def terminal(n,q):
        offset,slope=coefficients[n]
        return offset+slope*q
    def evaluate_policy(policy):
        # Aggregate best-response action values per private holding and public node.
        def br(player):
            def rec(n,weighted):
                s,aa,ch=nodes[n]
                if aa is None:return sum(w*terminal(n,q) for i,j,w,q in weighted)
                actor=s.pending[0]
                if actor==player:
                    groups=defaultdict(list)
                    for d in weighted:groups[d[actor]].append(d)
                    return sum((max if player==0 else min)(rec(c,g) for c in ch) for g in groups.values())
                return sum(rec(c,[(i,j,w*policy[n,(i,j)[actor]][k],q) for i,j,w,q in weighted])
                           for k,c in enumerate(ch))
            return rec(0,deals)
        def value(n,d):
            s,aa,ch=nodes[n];i,j,w,q=d
            if aa is None:return terminal(n,q)
            return sum(p*value(c,d) for p,c in zip(policy[n,(i,j)[s.pending[0]]],ch))
        v=sum(d[2]*value(0,d) for d in deals)
        lo,hi=br(1),br(0)
        need(lo-1e-8<=v<=hi+1e-8,"Invalid best-response certificate")
        return v,lo,hi
    convergence=[]
    for t in range(1,iterations+1):
        policy={k:normalize(v) for k,v in regrets.items()}
        delta={k:[0.]*len(v) for k,v in regrets.items()}
        # Own realization reach only for average strategy. Deal marginals are
        # fixed across iterations and cancel within each infoset.
        def walk(n,d,r0,r1):
            s,aa,ch=nodes[n];i,j,w,q=d
            if aa is None:return terminal(n,q)
            actor=s.pending[0];key=(n,(i,j)[actor]);p=policy[key]
            vals=[walk(c,d,r0*x if actor==0 else r0,r1*x if actor==1 else r1) for x,c in zip(p,ch)]
            v=sum(x*y for x,y in zip(p,vals))
            own,other=(r0,r1) if actor==0 else (r1,r0)
            for k,x in enumerate(p):
                delta[key][k]+=w*other*(vals[k]-v)*(1 if actor==0 else -1)
                sums[key][k]+=t*w*own*x
            return v
        for d in deals:walk(0,d,1.,1.)
        for k,v in regrets.items():
            regrets[k]=[max(0.,a+b) for a,b in zip(v,delta[k])]
        if check_every and t%check_every==0 and t<iterations:
            candidate={k:normalize(v) for k,v in sums.items()}
            _,lower,upper=evaluate_policy(candidate)
            gap=max(0.,upper-lower)
            convergence.append(dict(iteration=t,gap_bb=gap))
            if gap<=target:break
    average={k:normalize(v) for k,v in sums.items()}
    v,lo,hi=evaluate_policy(average)
    # Conditional on opponent reach, not own historical action probability.
    # EV is measured from this decision: add back the actor's sunk contribution.
    masses=defaultdict(float); totals={k:[0.]*len(p) for k,p in average.items()}
    def collect(n,d,r0,r1):
        state,aa,ch=nodes[n];i,j,w,q=d
        if aa is None:return terminal(n,q)
        actor=state.pending[0];key=(n,(i,j)[actor]);p=average[key]
        vals=[collect(c,d,r0*x if actor==0 else r0,r1*x if actor==1 else r1) for x,c in zip(p,ch)]
        weight=w*(r1 if actor==0 else r0)
        masses[key]+=weight
        for k,value in enumerate(vals):
            totals[key][k]+=weight*((value if actor==0 else -value)+state.paid[actor]/bb)
        return sum(x*y for x,y in zip(p,vals))
    for d in deals:collect(0,d,1.,1.)
    def action_ev(key,k):
        return totals[key][k]/masses[key] if masses[key]>0 else None
    return dict(version=VERSION,variant=5,iterations=t,iteration_budget=iterations,nodes=len(nodes),
                convergence_checks=convergence,early_stopped=t<iterations,
                ev_baseline="decision_sunk_contributions_excluded",
                ev_scope="fixed_average_policy_and_supplied_equity_matrix",
                value_sb_bb=v,best_response_lower_bb=lo,best_response_upper_bb=hi,
                nash_gap_bb=max(0.,hi-lo),target_reached=hi-lo<=target,
                policy=[dict(node=n,holding=h,position=nodes[n][0].actor,
                             opponent_reach_mass=masses[n,h],
                             actions=[dict(action=a,amount=b,frequency=p,ev_bb=action_ev((n,h),k)) for k,((a,b),p) in enumerate(zip(nodes[n][1],freq))])
                        for (n,h),freq in sorted(average.items())],
                tree=[dict(node=n,position=s.actor,children=list(ch),paid=list(s.paid),status=s.status)
                      for n,(s,aa,ch) in enumerate(nodes)],
                scope="HU preflop restricted sizings, zero rake, showdown-only continuation",
                certificate_conditional_on_equity_matrix=True,gto_solution=False)

def selftest():
    for q in (0.,.5,1.):
        r=solve({"SB":2,"BB":2},1,2,[(0,0,1,q)],iterations=500)
        assert r["nash_gap_bb"]<.01
        assert abs(r["value_sb_bb"]-max(-.5,2*q-1))<.01
    r=solve({"SB":10,"BB":10},1,2,[(0,0,1,.8),(1,0,1,.2)],iterations=500)
    assert r["best_response_lower_bb"]<=r["value_sb_bb"]+1e-8
    assert all(abs(sum(a["frequency"] for a in p["actions"])-1)<1e-9 for p in r["policy"])
    for row in r["policy"]:
        for action in row["actions"]:
            if action["action"]=="fold" and action["ev_bb"] is not None:
                assert abs(action["ev_bb"])<1e-9
    r=solve({"SB":2,"BB":2},1,2,[(0,0,1,.75)],iterations=100)
    root=r["policy"][0]["actions"]
    assert abs(next(a["ev_bb"] for a in root if a["action"]=="call")-1.)<1e-9
    r=solve({"SB":2,"BB":2},1,2,[(0,0,1,.75)],iterations=500,check_every=50)
    assert r["early_stopped"] and r["target_reached"] and r["iterations"]<500
    print("HU CFR checks passed")

if __name__=="__main__":selftest()
