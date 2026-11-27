"""Offline restricted HU river CFR+ with independent utilities under explicit rake."""
from collections import defaultdict
from fractions import Fraction
from math import isfinite
from plo5_post_gto_context import normalize, identity
from plo5_post_gto_tree import start, actions, step
from plo5_post_gto_rake import settle
from plo5_evaluator import evaluate
from plo5_pre_gto_context import need

VERSION = 'river-rake-cfr-v1'


def solve(context, iterations=500, pot_bps=(5000, 10000), node_limit=2000,
          max_work=20000000, *, rake_on_fold):
    c = normalize(context)
    need(len(c['seats']) == 2 and len(c['board']) == 5 and all(c['stacks'].values()), 'HU river only')
    need(type(rake_on_fold) is bool, 'Explicit fold rake rule required')
    need(type(iterations) is int and 1 <= iterations <= 50000, 'Invalid iterations')
    need(type(node_limit) is int and 1 <= node_limit <= 10000, 'Invalid node budget')
    need(type(max_work) is int and 1 <= max_work <= 100000000, 'Invalid work budget')
    rows = [c['ranges'][p] for p in c['seats']]
    need(len(rows[0])*len(rows[1]) <= 4096, 'Pair budget exceeded')
    hs = [[tuple(x['cards']) for x in r] for r in rows]
    ranks = [[evaluate(h, c['board'])['rank'] for h in r] for r in hs]
    pairs = [(i,j,rows[0][i]['weight']*rows[1][j]['weight'],
              int(ranks[0][i]>ranks[1][j])+Fraction(1,2)*int(ranks[0][i]==ranks[1][j]))
             for i,h in enumerate(hs[0]) for j,k in enumerate(hs[1]) if not set(h)&set(k)]
    mass = sum(d[2] for d in pairs)
    need(mass>0, 'No legal joint deals')
    pairs = [(i,j,w/mass,q) for i,j,w,q in pairs]
    nodes = []
    def build(s):
        need(len(nodes)<node_limit, 'Tree budget exceeded')
        n=len(nodes); nodes.append(None)
        aa=actions(s,pot_bps) if s.pending else ()
        ch=tuple(build(step(s,s.actor,a,b)) for a,b in aa)
        nodes[n]=(s,aa,ch)
        return n
    build(start(context))
    need(len(nodes)*len(pairs)*(iterations+5)<=max_work, 'Work budget exceeded')
    # Only three possible showdown shares: avoid per-deal Fraction settlement.
    terminal={n:{q:tuple(map(float,settle(s,q,c['rake_bps'],c['rake_cap'],rake_on_fold=rake_on_fold)['utility_bb']))
                 for q in (0,Fraction(1,2),1)} for n,(s,aa,ch) in enumerate(nodes) if not aa}
    regret={(n,h):[0.]*len(aa) for n,(s,aa,ch) in enumerate(nodes) if aa for h in {d[s.pending[0]] for d in pairs}}
    avg={k:[0.]*len(v) for k,v in regret.items()}
    def norm(v):
        total=sum(v)
        return [x/total for x in v] if total else [1/len(v)]*len(v)
    # Both utilities propagated, rather than negating seat 0 utility for seat 1.
    for t in range(1,iterations+1):
        pol={k:norm(v) for k,v in regret.items()}
        delta={k:[0.]*len(v) for k,v in regret.items()}
        def walk(n,d,r0,r1):
            s,aa,ch=nodes[n]; i,j,w,q=pairs[d]
            if not aa:return terminal[n][q]
            p=s.pending[0]; key=(n,(i,j)[p]); pr=pol[key]
            vals=[walk(k,d,r0*x if p==0 else r0,r1*x if p==1 else r1) for k,x in zip(ch,pr)]
            mean=tuple(sum(x*v[z] for x,v in zip(pr,vals)) for z in (0,1))
            for a,x in enumerate(pr):
                delta[key][a]+=w*(r1 if p==0 else r0)*(vals[a][p]-mean[p])
                avg[key][a]+=t*w*(r0 if p==0 else r1)*x
            return mean
        for d in range(len(pairs)):walk(0,d,1.,1.)
        for k in regret:regret[k]=[max(0.,x+y) for x,y in zip(regret[k],delta[k])]
    pol={k:norm(v) for k,v in avg.items()}
    masses=defaultdict(float); totals={k:[0.]*len(v) for k,v in pol.items()}
    def collect(n,d,r0,r1):
        s,aa,ch=nodes[n]; i,j,w,q=pairs[d]
        if not aa:return terminal[n][q]
        p=s.pending[0]; key=(n,(i,j)[p]); pr=pol[key]
        vals=[collect(k,d,r0*x if p==0 else r0,r1*x if p==1 else r1) for k,x in zip(ch,pr)]
        weight=w*(r1 if p==0 else r0); masses[key]+=weight
        for a,v in enumerate(vals):totals[key][a]+=weight*(v[p]+s.total_paid[p]/s.bb)
        return tuple(sum(x*v[z] for x,v in zip(pr,vals)) for z in (0,1))
    values=[0.,0.]
    for d,(_,_,w,_) in enumerate(pairs):
        v=collect(0,d,1.,1.)
        for p in (0,1):values[p]+=w*v[p]
    def br(p):
        def rec(n,weighted):
            s,aa,ch=nodes[n]
            if not aa:return sum(w*terminal[n][pairs[d][3]][p] for d,w in weighted)
            actor=s.pending[0]
            if actor==p:
                groups=defaultdict(list)
                for d,w in weighted:groups[pairs[d][p]].append((d,w))
                return sum(max(rec(k,g) for k in ch) for g in groups.values())
            return sum(rec(k,[(d,w*pol[n,pairs[d][actor]][a]) for d,w in weighted]) for a,k in enumerate(ch))
        return rec(0,[(d,w) for d,(_,_,w,_) in enumerate(pairs)])
    best=[br(0),br(1)]
    need(all(isfinite(v) for v in values+best) and all(b>=v-1e-8 for b,v in zip(best,values)), 'Best response inconsistency')
    gains=[max(0.,b-v) for b,v in zip(best,values)]
    return dict(variant=5,backend='python-rake',engine_version=VERSION,context_key=identity(context),
                iterations=iterations,nodes=len(nodes),legal_pairs=len(pairs),rake_on_fold=rake_on_fold,
                rake_bps=c['rake_bps'],rake_cap=c['rake_cap'],values_bb=values,best_responses_bb=best,
                unilateral_gains_bb=gains,nashconv_bb=sum(gains),nashconv_fraction_of_pot=sum(gains)/(c['pot']/c['bb']),
                expected_rake_bb=max(0.,c['pot']/c['bb']-sum(values)),gto_solution=False,
                scope='Restricted HU river, variable-sum CFR+ heuristic; no convergence guarantee',
                policy=[dict(node=n,position=nodes[n][0].actor,holding=list(hs[nodes[n][0].pending[0]][h]),
                    opponent_reach_mass=masses[n,h],actions=[dict(action=a,amount=b,frequency=x,
                    ev_bb=totals[n,h][k]/masses[n,h] if masses[n,h]>0 else None)
                    for k,((a,b),x) in enumerate(zip(nodes[n][1],v))]) for (n,h),v in sorted(pol.items())])
