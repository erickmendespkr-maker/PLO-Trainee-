"""Exact-chance restricted offline HU turn/river CFR+; no future-card infosets."""
from collections import defaultdict
from math import isfinite
from plo5_post_gto_context import normalize, identity, DECK
from plo5_post_gto_tree import start, actions, step, advance
from plo5_evaluator import evaluate
from plo5_pre_gto_context import need

VERSION = 'turn-river-cfr-v1'


def solve(context, iterations=100, pot_bps=(), *, rake_on_fold, node_limit=5000,
          max_work=20000000, max_pairs=256):
    c = normalize(context)
    need(len(c['board']) == 4 and len(c['seats']) == 2 and all(c['stacks'].values()), 'HU turn only')
    need(type(rake_on_fold) is bool, 'Explicit fold rake rule required')
    for x, hi in ((iterations,50000),(node_limit,10000),(max_work,100000000),(max_pairs,4096)):
        need(type(x) is int and 1 <= x <= hi, 'Invalid budget')
    rows = [c['ranges'][p] for p in c['seats']]
    need(len(rows[0])*len(rows[1]) <= max_pairs, 'Pair budget exceeded')
    hands = [[tuple(r['cards']) for r in rr] for rr in rows]
    pairs = [(i,j,rows[0][i]['weight']*rows[1][j]['weight']) for i,h in enumerate(hands[0])
             for j,k in enumerate(hands[1]) if not set(h)&set(k)]
    mass = sum(w for i,j,w in pairs)
    need(mass > 0, 'No legal joint deals')
    # Predeal a hidden river; only the public chance node may reveal it.
    deals = []; rank = {}; by_card = defaultdict(list)
    for i,j,w in pairs:
        for card in sorted(DECK-set(c['board'])-set(hands[0][i])-set(hands[1][j])):
            d=len(deals); deals.append((i,j,w/(mass*38),card)); by_card[card].append(d)
    need(len(deals)==38*len(pairs), 'Invalid chance count')
    nodes=[]; work=0
    def build(s, ds, history):
        nonlocal work
        work+=len(ds)
        need(len(nodes)<node_limit and work*(iterations+5)<=max_work, 'Tree/work budget exceeded')
        n=len(nodes); nodes.append(None)
        aa=actions(s,pot_bps) if s.pending else ()
        if aa:
            ch=tuple(build(step(s,s.actor,a,b),ds,history+[(s.actor,a,b)]) for a,b in aa)
        elif s.status=='chance_transition':
            ch={card:build(advance(s,card),[d for d in ds if deals[d][3]==card],history+[('chance',card,0)])
                for card in sorted(by_card) if any(deals[d][3]==card for d in ds)}
        else:ch=()
        nodes[n]=(s,aa,ch,history,ds)
        return n
    build(start(context),list(range(len(deals))),[])
    def payoff(s,d):
        i,j,w,card=deals[d]; m=min(s.total_paid); contested=s.base_pot+2*m
        folded=len(s.active)==1
        fee=min(c['rake_cap'],contested*c['rake_bps']//10000) if not folded or rake_on_fold else 0
        if folded:q=float(s.active[0]==0)
        else:
            for p,h in enumerate((i,j)):
                key=(p,h,card)
                if key not in rank:rank[key]=evaluate(hands[p][h],list(c['board'])+[card])['rank']
            a,b=rank[0,i,card],rank[1,j,card];q=1. if a>b else .5 if a==b else 0.
        net=contested-fee
        return ((q*net-m)/s.bb,((1-q)*net-m)/s.bb)
    terminal={n:{d:payoff(s,d) for d in ds} for n,(s,aa,ch,_,ds) in enumerate(nodes) if not ch}
    regret={(n,h):[0.]*len(aa) for n,(s,aa,ch,_,ds) in enumerate(nodes) if aa
            for h in {deals[d][s.pending[0]] for d in ds}}
    avg={k:[0.]*len(v) for k,v in regret.items()}
    def norm(v):
        z=sum(v); return [x/z for x in v] if z else [1/len(v)]*len(v)
    def walk(n,d,r0,r1,visit):
        s,aa,ch,_,_=nodes[n]; i,j,w,card=deals[d]
        if not ch:return terminal[n][d]
        if not aa:return walk(ch[card],d,r0,r1,visit)
        p=s.pending[0]; key=(n,(i,j)[p]); pr=pol[key]
        vals=[walk(k,d,r0*x if p==0 else r0,r1*x if p==1 else r1,visit) for k,x in zip(ch,pr)]
        mean=tuple(sum(x*v[z] for x,v in zip(pr,vals)) for z in (0,1))
        visit(key,p,s,w,r0,r1,pr,vals,mean)
        return mean
    for t in range(1,iterations+1):
        pol={k:norm(v) for k,v in regret.items()}; delta={k:[0.]*len(v) for k,v in regret.items()}
        def update(key,p,s,w,r0,r1,pr,vals,mean):
            for a,x in enumerate(pr):
                delta[key][a]+=w*(r1 if p==0 else r0)*(vals[a][p]-mean[p])
                avg[key][a]+=t*w*(r0 if p==0 else r1)*x
        for d in range(len(deals)):walk(0,d,1.,1.,update)
        for k in regret:regret[k]=[max(0.,x+y) for x,y in zip(regret[k],delta[k])]
    pol={k:norm(v) for k,v in avg.items()}
    masses=defaultdict(float); totals={k:[0.]*len(v) for k,v in pol.items()}
    def collect(key,p,s,w,r0,r1,pr,vals,mean):
        weight=w*(r1 if p==0 else r0);masses[key]+=weight
        for a,v in enumerate(vals):totals[key][a]+=weight*(v[p]+s.total_paid[p]/s.bb)
    values=[0.,0.]
    for d,(_,_,w,_) in enumerate(deals):
        v=walk(0,d,1.,1.,collect)
        for p in (0,1):values[p]+=w*v[p]
    def br(p):
        def rec(n,weighted):
            s,aa,ch,_,_=nodes[n]
            if not ch:return sum(w*terminal[n][d][p] for d,w in weighted)
            if not aa:
                groups=defaultdict(list)
                for d,w in weighted:groups[deals[d][3]].append((d,w))
                return sum(rec(ch[card],g) for card,g in groups.items())
            actor=s.pending[0]
            if actor==p:
                groups=defaultdict(list)
                for d,w in weighted:groups[deals[d][p]].append((d,w))
                return sum(max(rec(k,g) for k in ch) for g in groups.values())
            return sum(rec(k,[(d,w*pol[n,deals[d][actor]][a]) for d,w in weighted]) for a,k in enumerate(ch))
        return rec(0,[(d,x[2]) for d,x in enumerate(deals)])
    best=[br(0),br(1)]; need(all(isfinite(x) for x in values+best) and all(b>=v-1e-8 for b,v in zip(best,values)), 'Best response inconsistency')
    gains=[max(0.,b-v) for b,v in zip(best,values)]
    return dict(variant=5,engine_version=VERSION,context_key=identity(context),rake_on_fold=rake_on_fold,
                iterations=iterations,pot_bps=list(pot_bps),nodes=len(nodes),legal_pairs=len(pairs),chance_outcomes=len(deals),work_per_iteration=work,
                values_bb=values,best_responses_bb=best,unilateral_gains_bb=gains,nashconv_bb=sum(gains),
                nashconv_fraction_of_pot=sum(gains)/(c['pot']/c['bb']),expected_rake_bb=max(0.,c['pot']/c['bb']-sum(values)),gto_solution=False,
                scope='Restricted HU turn-river exact chance; variable-sum heuristic with rake',
                tree=[dict(node=n,board=list(s.board),position=s.actor,status=s.status,history=[list(e) for e in hist],
                           children=ch if isinstance(ch,dict) else list(ch)) for n,(s,aa,ch,hist,ds) in enumerate(nodes)],
                policy=[dict(node=n,position=nodes[n][0].actor,holding=list(hands[nodes[n][0].pending[0]][h]),opponent_reach_mass=masses[n,h],
                    actions=[dict(action=a,amount=b,frequency=x,ev_bb=totals[n,h][k]/masses[n,h] if masses[n,h]>0 else None)
                    for k,((a,b),x) in enumerate(zip(nodes[n][1],v))]) for (n,h),v in sorted(pol.items())])
