"""Restricted HU river CFR+ with legal postflop betting tree.
Zero rake, explicit physical ranges, no pre-existing side pots.
All utilities in BB, initial pot included in winner payoff.
"""
from collections import defaultdict
from math import isfinite
from plo5_post_gto_context import normalize,identity
from plo5_post_gto_tree import start,actions,step
from plo5_evaluator import evaluate
from plo5_pre_gto_context import need

def solve(context,iterations=500,pot_bps=(5000,10000),node_limit=2000,max_work=20000000,*,cfr_executable=None,native_timeout=120):
    c=normalize(context)
    need(len(c["seats"])==2 and len(c["board"])==5 and c["rake_bps"]==0,"HU zero-rake river only")
    need(type(iterations) is int and 1<=iterations<=50000,"Invalid iterations")
    need(type(node_limit) is int and 1<=node_limit<=10000,"Invalid node budget")
    need(type(max_work) is int and 1<=max_work<=100000000,"Invalid work budget")
    need(all(c["stacks"][p]>0 for p in c["seats"]),"Both seats must have chips")
    rows=[c["ranges"][p] for p in c["seats"]]
    need(len(rows[0])*len(rows[1])<=4096,"Pair budget exceeded")
    hs=[[tuple(x["cards"]) for x in r] for r in rows]
    ranks=[[evaluate(h,c["board"])["rank"] for h in r] for r in hs]
    pairs=[];mass=0
    for i,h in enumerate(hs[0]):
        for j,k in enumerate(hs[1]):
            if set(h)&set(k):continue
            w=rows[0][i]["weight"]*rows[1][j]["weight"]
            q=(1. if ranks[0][i]>ranks[1][j] else .5 if ranks[0][i]==ranks[1][j] else 0.)
            pairs.append((i,j,w,q));mass+=w
    need(mass>0,"No legal joint deals")
    pairs=[(i,j,w/mass,q) for i,j,w,q in pairs]
    nodes=[]
    def build(s):
        need(len(nodes)<node_limit,"Tree budget exceeded")
        i=len(nodes);nodes.append(None)
        aa=actions(s,pot_bps) if s.pending else ()
        ch=tuple(build(step(s,s.actor,a,b)) for a,b in aa)
        nodes[i]=(s,aa,ch)
        return i
    build(start(context))
    need(len(nodes)*len(pairs)*(iterations+5)<=max_work,"Work budget exceeded")
    def utility(s,q):
        a,b=s.total_paid
        if len(s.active)==1:q=float(s.active[0]==0)
        # Return uncalled excess; only equal contributions contest the root pot.
        m=min(a,b)
        return (q*(s.base_pot+2*m)-m)/s.bb
    terminal={i:tuple(utility(s,q) for _,_,_,q in pairs) for i,(s,aa,ch) in enumerate(nodes) if not aa}
    regret={};avg={}
    for n,(s,aa,ch) in enumerate(nodes):
        if aa:
            p=s.pending[0]
            for h in {d[p] for d in pairs}:
                regret[n,h]=[0.]*len(aa);avg[n,h]=[0.]*len(aa)
    def norm(x):
        t=sum(x);return [v/t for v in x] if t else [1/len(x)]*len(x)
    if cfr_executable is not None:
        from plo5_pre_gto_cfr_native import train
        native_nodes=[(s,aa if aa else None,ch) for s,aa,ch in nodes]
        coefficients={}
        for n,(s,aa,ch) in enumerate(nodes):
            if not aa:
                coefficients[n]=(utility(s,0.),utility(s,1.)-utility(s,0.))
        pol=train(cfr_executable,native_nodes,pairs,coefficients,regret,iterations,timeout=native_timeout)
    else:
        for t in range(1,iterations+1):
            pol={k:norm(v) for k,v in regret.items()}
            delta={k:[0.]*len(v) for k,v in regret.items()}
            def walk(n,d,r0,r1):
                s,aa,ch=nodes[n];i,j,w,q=pairs[d]
                if not aa:return terminal[n][d]
                p=s.pending[0];key=(n,(i,j)[p]);pr=pol[key]
                vals=[walk(k,d,r0*x if p==0 else r0,r1*x if p==1 else r1) for k,x in zip(ch,pr)]
                v=sum(x*y for x,y in zip(pr,vals))
                for k,x in enumerate(pr):
                    delta[key][k]+=w*(r1 if p==0 else -r0)*(vals[k]-v)
                    avg[key][k]+=t*w*(r0 if p==0 else r1)*x
                return v
            for d in range(len(pairs)):walk(0,d,1.,1.)
            for k in regret:regret[k]=[max(0.,a+b) for a,b in zip(regret[k],delta[k])]
        pol={k:norm(v) for k,v in avg.items()}
    masses=defaultdict(float);totals={k:[0.]*len(v) for k,v in pol.items()}
    def collect(n,d,r0,r1):
        s,aa,ch=nodes[n];i,j,w,q=pairs[d]
        if not aa:return terminal[n][d]
        p=s.pending[0];key=(n,(i,j)[p]);pr=pol[key]
        vals=[collect(k,d,r0*x if p==0 else r0,r1*x if p==1 else r1) for k,x in zip(ch,pr)]
        weight=w*(r1 if p==0 else r0);masses[key]+=weight
        for k,v in enumerate(vals):
            # Root-pot share utility, plus own contribution already sunk at node.
            own=v if p==0 else s.base_pot/s.bb-v
            totals[key][k]+=weight*(own+s.total_paid[p]/s.bb)
        return sum(x*y for x,y in zip(pr,vals))
    value=sum(w*collect(0,d,1.,1.) for d,(_,_,w,_) in enumerate(pairs))
    def br(p):
        def rec(n,weighted):
            s,aa,ch=nodes[n]
            if not aa:return sum(w*terminal[n][d] for d,w in weighted)
            actor=s.pending[0]
            if actor==p:
                groups=defaultdict(list)
                for d,w in weighted:groups[pairs[d][p]].append((d,w))
                choose=max if p==0 else min
                return sum(choose(rec(k,g) for k in ch) for g in groups.values())
            return sum(rec(k,[(d,w*pol[n,pairs[d][actor]][a]) for d,w in weighted]) for a,k in enumerate(ch))
        return rec(0,[(d,w) for d,(_,_,w,_) in enumerate(pairs)])
    upper,lower=br(0),br(1)
    need(all(isfinite(x) for x in (value,upper,lower)) and lower<=value+1e-8 and value<=upper+1e-8,"Best response inconsistency")
    return dict(variant=5,backend="native" if cfr_executable is not None else "python",context_key=identity(context),iterations=iterations,nodes=len(nodes),legal_pairs=len(pairs),value_bb=value,best_response_lower_bb=lower,best_response_upper_bb=upper,nash_gap_bb=max(0.,upper-lower),gap_fraction_of_pot=max(0.,upper-lower)/(c["pot"]/c["bb"]),gto_solution=False,scope="Restricted HU zero-rake river, explicit ranges and discrete sizings",policy=[dict(node=n,position=nodes[n][0].actor,holding=list(hs[nodes[n][0].pending[0]][h]),opponent_reach_mass=masses[n,h],actions=[dict(action=a,amount=b,frequency=x,ev_bb=totals[n,h][k]/masses[n,h] if masses[n,h]>0 else None) for k,((a,b),x) in enumerate(zip(nodes[n][1],v))]) for (n,h),v in sorted(pol.items())])
