"""Restricted multiway PLO5 preflop CFR prototype.
Explicit chance deals contain physical holdings and a complete sampled board.
Players never observe the board or other holdings in their information sets.
Configurable capped rake; showdown-only continuation; discrete legal raises.
No convergence guarantee in multiplayer games.
"""
from collections import defaultdict
from math import isfinite
from plo5_pre_gto_context import cards, need
from plo5_pre_gto_tree import start, actions, step
from plo5_pre_gto_equity import DECK
from plo5_pre_gto_rules import rake_config, rake_amount, sized_actions
from plo5_evaluator import evaluate

VERSION="pre-gto-multiway-v3"

def settlement(state,ranks,config=None):
    """Net chip EV, fractional split pots, uncalled excess returned."""
    need(not state.pending,"Nonterminal settlement")
    paid=state.paid;n=len(paid)
    out=[-float(p) for p in paid]
    config=rake_config() if config is None else rake_config(**config)
    # Unique highest contribution is uncalled excess, never raked.
    ordered=sorted(paid,reverse=True)
    contested=sum(paid)-(ordered[0]-ordered[1])
    fee=rake_amount(contested,config,len(state.active)==1)
    if len(state.active)==1:
        out[state.active[0]]+=sum(paid)-fee
        return tuple(out)
    remaining_fee=fee
    previous=0
    for level in sorted(set(paid)-{0}):
        contributors=[i for i,p in enumerate(paid) if p>=level]
        pool=(level-previous)*len(contributors);previous=level
        if len(contributors)==1:
            out[contributors[0]]+=pool
            continue
        deduction=min(pool,remaining_fee);pool-=deduction;remaining_fee-=deduction
        eligible=[i for i in contributors if not state.folded[i]]
        need(eligible,"Invalid side pot without eligible players")
        best=max(ranks[i] for i in eligible)
        winners=[i for i in eligible if ranks[i]==best]
        for i in winners:out[i]+=pool/len(winners)
    need(remaining_fee==0 and abs(sum(out)+fee)<=1e-7*max(1,sum(paid)),"Chip conservation failure")
    return tuple(out)

def prepare(deals,n):
    need(type(deals) is list and 1<=len(deals)<=2048,"Invalid chance deal budget")
    raw=[];mass=0
    for d in deals:
        need(type(d) is dict and set(d)=={"hands","board","weight"},"Invalid deal")
        need(type(d["hands"]) is list and len(d["hands"])==n,"Wrong seats")
        hands=tuple(tuple(cards(h)) for h in d["hands"])
        board=d["board"];w=d["weight"]
        need(type(board) is list and len(board)==5 and all(c in DECK for c in board),"Invalid board")
        need(len(set(board).union(*hands))==5*(n+1),"Duplicate cards")
        need(type(w) is int and 1<=w<=10**12,"Invalid chance weight")
        ranks=tuple(evaluate(h,board)["rank"] for h in hands)
        raw.append((hands,w,ranks));mass+=w
    return [(h,w/mass,r) for h,w,r in raw]

def solve(stacks,sb,bb,deals,*,iterations=100,node_limit=10000,max_work=10000000,sizings=(),target_bb=.01,pot_bps=(),rake_bps=0,rake_cap=0,rake_on_fold=False,profile=None):
    root=start(stacks,sb,bb);n=len(root.order)
    need(2<=n<=6,"Expected 2-6 seats")
    config=rake_config(rake_bps,rake_cap,rake_on_fold)
    need(type(iterations) is int and 1<=iterations<=5000,"Invalid iterations")
    need(type(node_limit) is int and 1<=node_limit<=100000,"Invalid node limit")
    need(type(max_work) is int and 1<=max_work<=100000000,"Invalid work budget")
    need(type(target_bb) in (float,int) and isfinite(target_bb) and target_bb>=0,"Invalid target")
    chance=prepare(deals,n);nodes=[]
    from plo5_pre_gto_profile import profile_actions
    need(profile is None or (not sizings and not pot_bps),"Ambiguous sizing configuration")
    def build(s,raises=0):
        need(len(nodes)<node_limit,"Tree node budget exceeded")
        i=len(nodes);nodes.append(None)
        aa=(sized_actions(s,sizings,pot_bps) if profile is None else profile_actions(s,raises,profile)) if s.pending else ()
        ch=tuple(build(step(s,s.actor,a,b),raises+(a=="raise")) for a,b in aa)
        nodes[i]=(s,aa,ch)
        return i
    build(root)
    need(len(nodes)*len(chance)*(iterations+n+3)<=max_work,"Traversal budget exceeded")
    terminal={}
    regret={};avg={}
    for i,(s,aa,ch) in enumerate(nodes):
        if not aa:
            for d,(_,_,r) in enumerate(chance):
                terminal[i,d]=tuple(v/bb for v in settlement(s,r,config))
        else:
            p=s.pending[0]
            for h in {h[p] for h,w,r in chance}:
                regret[i,h]=[0.]*len(aa);avg[i,h]=[0.]*len(aa)
    def norm(v):
        t=sum(v)
        return [x/t for x in v] if t else [1/len(v)]*len(v)
    for t in range(1,iterations+1):
        policy={k:norm(v) for k,v in regret.items()}
        delta={k:[0.]*len(v) for k,v in regret.items()}
        def walk(i,d,reach):
            s,aa,ch=nodes[i];h,w,r=chance[d]
            if not aa:return terminal[i,d]
            p=s.pending[0];key=(i,h[p]);probs=policy[key]
            values=[]
            for c,x in zip(ch,probs):
                rr=list(reach);rr[p]*=x;values.append(walk(c,d,rr))
            v=tuple(sum(x*y[j] for x,y in zip(probs,values)) for j in range(n))
            other=w
            for j in range(n):
                if j!=p:other*=reach[j]
            for k,x in enumerate(probs):
                delta[key][k]+=other*(values[k][p]-v[p])
                avg[key][k]+=t*w*reach[p]*x
            return v
        for d in range(len(chance)):walk(0,d,[1.]*n)
        for k in regret:regret[k]=[max(0.,x+y) for x,y in zip(regret[k],delta[k])]
    policy={k:norm(v) for k,v in avg.items()}
    def expected(i,d):
        s,aa,ch=nodes[i];h,w,r=chance[d]
        if not aa:return terminal[i,d]
        probs=policy[i,h[s.pending[0]]];vals=[expected(c,d) for c in ch]
        return tuple(sum(x*y[j] for x,y in zip(probs,vals)) for j in range(n))
    value=[0.]*n
    for d,(_,w,_) in enumerate(chance):
        for j,x in enumerate(expected(0,d)):value[j]+=w*x
    def best_response(p):
        def rec(i,weighted):
            s,aa,ch=nodes[i]
            if not aa:return sum(w*terminal[i,d][p] for d,w in weighted)
            actor=s.pending[0]
            if actor==p:
                groups=defaultdict(list)
                for d,w in weighted:groups[chance[d][0][p]].append((d,w))
                return sum(max(rec(c,g) for c in ch) for g in groups.values())
            return sum(rec(c,[(d,w*policy[i,chance[d][0][actor]][k]) for d,w in weighted])
                       for k,c in enumerate(ch))
        return rec(0,[(d,w) for d,(_,w,_) in enumerate(chance)])
    br=[best_response(p) for p in range(n)]
    need(all(b>=v-1e-8 for b,v in zip(br,value)),"Best response inconsistency")
    gains=[max(0,b-v) for b,v in zip(br,value)]
    masses=defaultdict(float)
    totals={key:[0.]*len(probs) for key,probs in policy.items()}
    def collect(i,d,reach):
        s,aa,ch=nodes[i];h,w,r=chance[d]
        if not aa:return terminal[i,d]
        p=s.pending[0];key=(i,h[p]);probs=policy[key]
        vals=[]
        for c,x in zip(ch,probs):
            rr=list(reach);rr[p]*=x;vals.append(collect(c,d,rr))
        weight=w
        for j in range(n):
            if j!=p:weight*=reach[j]
        masses[key]+=weight
        for k,v in enumerate(vals):totals[key][k]+=weight*(v[p]+s.paid[p]/bb)
        return tuple(sum(x*v[j] for x,v in zip(probs,vals)) for j in range(n))
    for d in range(len(chance)):collect(0,d,[1.]*n)
    def action_ev(key,k):
        return totals[key][k]/masses[key] if masses[key]>0 else None

    return dict(version=VERSION,variant=5,positions=list(root.order),nodes=len(nodes),
                chance_deals=len(chance),iterations=iterations,value_bb=value,
                best_response_bb=br,unilateral_gain_bb=gains,nashconv_bb=sum(gains),
                target_reached=sum(gains)<=target_bb,gto_solution=False,
                certificate_scope="finite supplied chance support and restricted sizing tree only",
                continuation="showdown_only",rake_modeled=True,rake=config,pot_bps=list(pot_bps),sizing_profile=profile,
                ev_baseline="decision_sunk_contributions_excluded",
                policy=[dict(node=i,holding=list(h),position=nodes[i][0].actor,
                             opponent_reach_mass=masses[i,h],
                             actions=[dict(action=a,amount=b,frequency=x,ev_bb=action_ev((i,h),k)) for k,((a,b),x) in enumerate(zip(nodes[i][1],v))])
                        for (i,h),v in sorted(policy.items())],
                tree=[dict(node=i,position=s.actor,children=list(ch),paid=list(s.paid),status=s.status)
                      for i,(s,aa,ch) in enumerate(nodes)])

def selftest():
    from dataclasses import replace
    s=start({"BTN":20,"SB":20,"BB":20},1,2)
    s=replace(s,paid=(5,10,15),pending=())
    assert settlement(s,(3,2,1))==(10.,0.,-10.)
    assert settlement(s,(3,3,1))==(2.5,7.5,-10.)
    hands=[list(DECK[i:i+5]) for i in (0,5,10)]
    board=list(DECK[15:20])
    r=solve({"BTN":2,"SB":2,"BB":2},1,2,[dict(hands=hands,board=board,weight=1)],iterations=50)
    assert abs(sum(r["value_bb"]))<1e-8
    assert all(abs(sum(a["frequency"] for a in x["actions"])-1)<1e-9 for x in r["policy"])
    s=replace(s,paid=(5,10,15),pending=())
    assert settlement(s,(3,2,1),rake_config(1000,2))==(8.,0.,-10.)
    print("Multiway solver analytical checks passed")

if __name__=="__main__":selftest()
