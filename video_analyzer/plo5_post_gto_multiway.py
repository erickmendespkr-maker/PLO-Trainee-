"""Bounded offline 2–6-seat PLO5 postflop CFR+ with exact physical chance.
No prior side pots; discrete legal betting sizes; no multiplayer Nash guarantee.
"""
from collections import defaultdict
from itertools import product, permutations
from math import prod, isfinite
from hashlib import sha256
import json
from plo5_pre_gto_context import need, cards, integer
from plo5_post_gto_context import normalize, identity, DECK
from plo5_post_gto_tree import start, actions, step, advance
from plo5_post_gto_multiway_ledger import settle
from plo5_evaluator import evaluate

VERSION='multiway-postflop-v1'


def prior(context, joint=None, max_deals=4096, max_candidates=1000000):
    c=normalize(context); n=len(c['seats'])
    need(type(max_deals) is int and 1<=max_deals<=4096,'Invalid deal budget')
    need(type(max_candidates) is int and 1<=max_candidates<=1000000,'Invalid candidate budget')
    ranges=[{tuple(r['cards']):r['weight'] for r in c['ranges'][p]} for p in c['seats']]
    out=[]; seen=set()
    if joint is None:
        need(prod(map(len,ranges))<=max_candidates,'Cartesian candidate budget exceeded')
        entries=((h,prod(r[k] for r,k in zip(ranges,h))) for h in product(*ranges))
    else:
        need(type(joint) is list and 0<len(joint)<=max_deals,'Invalid explicit joint prior')
        def explicit():
            for row in joint:
                need(type(row) is dict and set(row)=={'holdings','weight'},'Invalid joint row')
                need(type(row['holdings']) is list and len(row['holdings'])==n,'Invalid joint seats')
                h=tuple(tuple(cards(x)) for x in row['holdings'])
                need(all(k in r for r,k in zip(ranges,h)),'Holding outside declared range')
                yield h,integer(row['weight'],1)
        entries=explicit()
    for h,w in entries:
        legal=len(set().union(*map(set,h)))==5*n
        if joint is not None:need(legal and h not in seen,'Invalid or duplicate explicit joint deal')
        if not legal:continue
        seen.add(h);out.append((h,w));need(len(out)<=max_deals,'Joint deal budget exceeded')
    need(bool(out),'No legal joint deals')
    return sorted(out)


def solve(context, iterations=100, pot_bps=(), *, rake_on_fold, joint=None,
          max_deals=4096, max_outcomes=100000, node_limit=100000, max_work=20000000,
          cfr_executable=None, native_timeout=120):
    c=normalize(context); n=len(c['seats']); board=tuple(c['board']); missing=5-len(board)
    need(all(c['stacks'].values()),'Root must have positive stacks; prior side pots unsupported')
    need(type(rake_on_fold) is bool,'Explicit fold rake rule required')
    for x,hi in ((iterations,50000),(max_outcomes,155648),(node_limit,100000),(max_work,100000000)):
        need(type(x) is int and 1<=x<=hi,'Invalid budget')
    rows=prior(context,joint,max_deals);mass=sum(w for h,w in rows)
    left=52-5*n-len(board);count=prod(range(left-missing+1,left+1))
    need(len(rows)*count<=max_outcomes,'Chance budget exceeded')
    deals=[]
    for h,w in rows:
        deck=sorted(DECK-set(board)-set().union(*map(set,h)))
        for runout in permutations(deck,missing):deals.append((h,w/(mass*count),runout))
    need(len(deals)==len(rows)*count,'Chance count mismatch')
    nodes=[];work=0
    def card(s,d):return deals[d][2][len(s.board)-len(board)]
    def build(s,ds,path):
        nonlocal work
        work+=len(ds);need(len(nodes)<node_limit and work<=1000000 and work*(iterations+5)<=max_work,'Tree/work budget exceeded')
        i=len(nodes);nodes.append(None);aa=actions(s,pot_bps) if s.pending else ()
        if aa:ch=tuple(build(step(s,s.actor,a,b),ds,path+((s.actor,a,b),)) for a,b in aa)
        elif s.status=='chance_transition':
            groups=defaultdict(list)
            for d in ds:groups[card(s,d)].append(d)
            ch={k:build(advance(s,k),v,path+(('chance',k,0),)) for k,v in sorted(groups.items())}
        else:ch=()
        nodes[i]=(s,aa,ch,path,ds);return i
    build(start(context),list(range(len(deals))),())
    ranks={};terminal={};settlements={}
    for i,(s,aa,ch,path,ds) in enumerate(nodes):
        if ch:continue
        terminal[i]={}
        for d in ds:
            h,w,runout=deals[d];final=tuple(sorted(board+runout));rr=[]
            for p,k in enumerate(h):
                if s.folded[p] or len(s.active)==1:rr.append(None);continue
                key=(k,final)
                if key not in ranks:ranks[key]=evaluate(k,final)['rank']
                rr.append(ranks[key])
            key=(s.total_paid,s.folded,tuple(rr))
            if key not in settlements:
                ledger=settle(s.base_pot,s.total_paid,s.folded,rr,c['rake_bps'],c['rake_cap'],rake_on_fold=rake_on_fold)
                settlements[key]=tuple(float(x/s.bb) for x in ledger['utility_chips'])
            terminal[i][d]=settlements[key]
    regret={(i,h):[0.]*len(aa) for i,(s,aa,ch,path,ds) in enumerate(nodes) if aa
            for h in {deals[d][0][s.pending[0]] for d in ds}}
    avg={k:[0.]*len(v) for k,v in regret.items()}
    def norm(v):
        z=sum(v);return [x/z for x in v] if z else [1/len(v)]*len(v)
    def walk(i,d,reach,visit):
        s,aa,ch,_,_=nodes[i];h,w,runout=deals[d]
        if not ch:return terminal[i][d]
        if not aa:return walk(ch[card(s,d)],d,reach,visit)
        p=s.pending[0];key=(i,h[p]);pr=pol[key]
        vals=[walk(k,d,reach[:p]+(reach[p]*x,)+reach[p+1:],visit) for k,x in zip(ch,pr)]
        mean=tuple(sum(x*v[z] for x,v in zip(pr,vals)) for z in range(n))
        visit(key,p,s,w,reach,pr,vals,mean);return mean
    ones=(1.,)*n
    if cfr_executable is not None:
        from plo5_multiway_native import train
        pol=train(cfr_executable,n,nodes,deals,terminal,regret,iterations,timeout=native_timeout)
    else:
        for t in range(1,iterations+1):
            pol={k:norm(v) for k,v in regret.items()};delta={k:[0.]*len(v) for k,v in regret.items()}
            def update(key,p,s,w,reach,pr,vals,mean):
                cf=w*prod(reach[:p]+reach[p+1:])
                for a,x in enumerate(pr):
                    delta[key][a]+=cf*(vals[a][p]-mean[p]);avg[key][a]+=t*w*reach[p]*x
            for d in range(len(deals)):walk(0,d,ones,update)
            for k in regret:regret[k]=[max(0.,x+y) for x,y in zip(regret[k],delta[k])]
        pol={k:norm(v) for k,v in avg.items()}
    masses=defaultdict(float);totals={k:[0.]*len(v) for k,v in pol.items()}
    def collect(key,p,s,w,reach,pr,vals,mean):
        cf=w*prod(reach[:p]+reach[p+1:]);masses[key]+=cf
        for a,v in enumerate(vals):totals[key][a]+=cf*(v[p]+s.total_paid[p]/s.bb)
    values=[0.]*n
    for d,(_,w,_) in enumerate(deals):
        for p,v in enumerate(walk(0,d,ones,collect)):values[p]+=w*v
    def br(p):
        def rec(i,weighted):
            s,aa,ch,_,_=nodes[i]
            if not ch:return sum(w*terminal[i][d][p] for d,w in weighted)
            if not aa:
                groups=defaultdict(list)
                for d,w in weighted:groups[card(s,d)].append((d,w))
                return sum(rec(ch[k],g) for k,g in groups.items())
            a=s.pending[0]
            if a==p:
                groups=defaultdict(list)
                for d,w in weighted:groups[deals[d][0][p]].append((d,w))
                return sum(max(rec(k,g) for k in ch) for g in groups.values())
            return sum(rec(k,[(d,w*pol[i,deals[d][0][a]][j]) for d,w in weighted]) for j,k in enumerate(ch))
        return rec(0,[(d,x[1]) for d,x in enumerate(deals)])
    best=[br(p) for p in range(n)];need(all(isfinite(x) for x in values+best) and all(b>=v-1e-8 for b,v in zip(best,values)),'Best response inconsistency')
    gains=[max(0.,b-v) for b,v in zip(best,values)]
    model=dict(context_key=identity(context),joint=rows,rake_on_fold=rake_on_fold,pot_bps=sorted(set(pot_bps)),version=VERSION)
    return dict(variant=5,engine_version=VERSION,model_key=sha256(json.dumps(model,sort_keys=True).encode()).hexdigest(),
                backend='native' if cfr_executable is not None else 'python',seats=c['seats'],iterations=iterations,nodes=len(nodes),legal_deals=len(rows),chance_outcomes=len(deals),work_per_iteration=work,
                values_bb=values,best_responses_bb=best,unilateral_gains_bb=gains,nashconv_bb=sum(gains),expected_rake_bb=max(0.,c['pot']/c['bb']-sum(values)),gto_solution=False,
                scope='Restricted exact-chance multiway CFR+ heuristic; no general Nash guarantee',
                tree=[dict(node=i,board=list(s.board),position=s.actor,status=s.status,history=[list(e) for e in path],children=ch if isinstance(ch,dict) else list(ch)) for i,(s,aa,ch,path,ds) in enumerate(nodes)],
                policy=[dict(node=i,position=nodes[i][0].actor,holding=list(h),opponent_reach_mass=masses[i,h],actions=[dict(action=a,amount=b,frequency=x,ev_bb=totals[i,h][j]/masses[i,h] if masses[i,h]>0 else None) for j,((a,b),x) in enumerate(zip(nodes[i][1],v))]) for (i,h),v in sorted(pol.items())])
