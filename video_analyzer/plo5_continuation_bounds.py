"""Conservative offline PLO5 local EV envelopes, not equilibrium certificates."""
from fractions import Fraction
from itertools import combinations
from math import comb
from functools import lru_cache
import hashlib
import json
from plo5_pre_gto_context import cards, integer, need
from plo5_post_gto_context import DECK
from plo5_post_gto_multiway_ledger import settle
from plo5_snapshot_replay import positions, reveal
from plo5_terminal_bounds import prefix, ratio
from plo5_selective_review import action_key, select, street_filter, STREETS
from plo5_evaluator import evaluate
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def board(s):return () if isinstance(s,pre.State) else s.board


def engine(s):return pre if isinstance(s,pre.State) else post


def paid(s):return s.paid if isinstance(s,pre.State) else s.total_paid


def base(s):return 0 if isinstance(s,pre.State) else s.base_pot


def legal(s):
    b=engine(s).bounds(s);c=b['to_call'];lo=b['raise_min'];hi=b['raise_max']
    basic=[('fold',0),('call',b['call_payment'])] if c else [('check',0)]
    kind='raise' if isinstance(s,pre.State) or c else 'bet'
    return basic,kind,lo,hi


def rational(pair):
    need(type(pair) is list and len(pair)==2,'Invalid likelihood')
    a,b=pair;integer(a);integer(b,1);need(a<=b,'Invalid likelihood')
    return Fraction(a,b)


def prior_at_decision(seed,events,index,config):
    """Condition a declared deal prior on past opponent action likelihoods and blockers.
    Hero actions are interventions. No likelihood is inferred from observed outcome.
    """
    s,h,actual=prefix(seed,events,index);hero=s.actor
    need(type(config) is dict and set(config)=={'prefix_sha256','hypotheses','rake_bps','rake_cap','rake_on_fold'},'Invalid continuation config')
    key=digest({'seed':seed,'events':events[:index]});need(config['prefix_sha256']==key,'Range prefix mismatch')
    opponents=[e for e in events[:index] if 'position' in e and e['position']!=hero]
    hs=config['hypotheses'];need(type(hs) is list and 1<=len(hs)<=8,'Invalid hypothesis count');out=[];ids=set()
    for q in hs:
        need(type(q) is dict and set(q)=={'id','provenance','deals'},'Invalid hypothesis')
        name=q['id'];src=q['provenance'];need(type(name) is str and 0<len(name)<=128 and name not in ids,'Invalid hypothesis ID');ids.add(name)
        need(type(src) is dict and set(src)=={'description','source_sha256'} and type(src['description']) is str and 0<len(src['description'])<=1024 and type(src['source_sha256']) is str and len(src['source_sha256'])==64 and all(c in '0123456789abcdef' for c in src['source_sha256']),'Missing declared provenance')
        ds=q['deals'];need(type(ds) is list and 1<=len(ds)<=128,'Invalid deal budget');seen=set();rows=[];total=Fraction(0)
        for d in ds:
            need(type(d) is dict and set(d)=={'holdings','weight','likelihoods'} and type(d['holdings']) is dict and set(d['holdings'])==set(s.order),'Full dealt roster required')
            hands=tuple(tuple(cards(d['holdings'][p])) for p in s.order);dead=set().union(*(set(k) for k in hands));need(len(dead)==5*len(s.order) and list(hands[s.order.index(hero)])==h and hands not in seen,'Invalid physical deal');seen.add(hands)
            weight=Fraction(integer(d['weight'],1));ls=d['likelihoods'];need(type(ls) is list and len(ls)==len(opponents),'Likelihood roster mismatch')
            for e,l in zip(opponents,ls):
                need(type(l) is dict and set(l)=={'event','probability'} and l['event']==e,'Likelihood event mismatch');weight*=rational(l['probability'])
            if weight and not dead.intersection(board(s)):rows.append((hands,weight));total+=weight
        need(total>0,'Zero conditional range mass');out.append((name,src,[(hands,w/total) for hands,w in sorted(rows)]))
    return s,h,actual,out,key


def envelopes(s,hero,deals,actions,*,rake_bps,rake_cap,rake_on_fold,max_nodes=2048,rank_worker=None):
    """Per-action budget. Relax hidden-information constraints: min/max over ALL
    future strategies, even clairvoyant ones; thus bounds, not optimal policy EV.
    Exact uniform public chance with residual branches bounded by chip conservation.
    """
    need(s.pending and s.actor==hero,'Expected Hero decision');need(type(max_nodes) is int and 1<=max_nodes<=16384,'Invalid node budget')
    need(integer(rake_bps)<=10000 and type(rake_on_fold) is bool,'Invalid rake rule');integer(rake_cap)
    i=s.order.index(hero);initial=s.remaining[i];total=s.pot+sum(s.remaining);lo=Fraction(-initial,s.bb);hi=Fraction(total-initial,s.bb)
    result={};stats={}
    for action,amount in actions:
        child=engine(s).step(s,hero,action,amount);visited=0;cutoffs=0;leaves=0
        @lru_cache(maxsize=2048)
        def ranks(hands,b):
            queries=[(h,b) for h in hands]
            return tuple((r['rank'],) for r in rank_worker.lookup(5,queries)) if rank_worker is not None else tuple(evaluate(h,b)['rank'] for h in hands)
        def limit(st):
            j=st.order.index(hero)
            if st.folded[j]:return (Fraction(st.remaining[j]-initial,s.bb),)*2
            return lo,hi
        def settle_value(st,deal,b):
            nonlocal leaves
            leaves+=1;j=st.order.index(hero);hs=tuple(deal[p] for p in st.order)
            rr=[None]*len(hs) if len(st.active)==1 else ranks(hs,tuple(b))
            z=settle(base(st),paid(st),st.folded,rr,rake_bps,rake_cap,rake_on_fold=rake_on_fold)
            return Fraction(st.remaining[j]-initial,s.bb)+(z['awards'][j]+z['returned'][j])/s.bb
        def visit(st,deal,depth=0):
            nonlocal visited,cutoffs
            j=st.order.index(hero)
            if st.folded[j]:return limit(st)
            if visited>=max_nodes or depth>=128:cutoffs+=1;return limit(st)
            visited+=1;status=st.status;b=board(st)
            if status in ('fold_terminal','river_showdown') or status=='all_in_showdown' and len(b)==5:
                v=settle_value(st,deal,b);return v,v
            if status=='decision':
                basic,kind,a,z=legal(st);n=len(basic)+(0 if a is None else z-a+1);lower=hi;upper=lo;done=0
                from itertools import chain
                for act,amt in chain(basic,() if a is None else ((kind,k) for k in range(a,z+1))):
                    if visited>=max_nodes:break
                    x,y=visit(engine(st).step(st,st.actor,act,amt),deal,depth+1);lower=min(lower,x);upper=max(upper,y);done+=1
                if done<n:cutoffs+=1;x,y=limit(st);lower=min(lower,x);upper=max(upper,y)
                return lower,upper
            need(status in ('flop_transition','chance_transition','all_in_showdown'),'Unknown state')
            dead=set(b).union(*(set(h) for h in deal.values()));deck=sorted(DECK-dead);k=5-len(b) if status=='all_in_showdown' else 3 if not b else 1;n=comb(len(deck),k);lower=upper=Fraction(0);done=0
            for draw in combinations(deck,k):
                if visited>=max_nodes:break
                if status=='all_in_showdown':
                    visited+=1;v=settle_value(st,deal,b+draw);x=y=v
                else:x,y=visit(reveal(st,list(draw)),deal,depth+1)
                lower+=x;upper+=y;done+=1
            if done<n:cutoffs+=1;x,y=limit(st);lower+=(n-done)*x;upper+=(n-done)*y
            return lower/n,upper/n
        a=z=Fraction(0);mass=Fraction(0)
        for hs,w in deals:
            if visited>=max_nodes:break
            x,y=visit(child,dict(zip(s.order,hs)));a+=w*x;z+=w*y;mass+=w
        if mass<1:cutoffs+=1;x,y=limit(child);a+=(1-mass)*x;z+=(1-mass)*y
        key=action_key([action,amount]);result[key]=(a,z);stats[key]=dict(nodes=visited,cutoffs=cutoffs,terminal_leaves=leaves)
        ranks.cache_clear()
    return result,stats


def evaluate_decision(seed,events,index,config,*,max_nodes=2048,rank_worker=None):
    s,h,actual,priors,key=prior_at_decision(seed,events,index,config);basic,kind,a,z=legal(s);count=len(basic)+(0 if a is None else z-a+1)
    # For large sizing spaces, explicitly mark the root action set incomplete.
    choices=basic+([] if a is None else [(kind,k) for k in (range(a,z+1) if count<=32 else sorted({a,z}))]);act,amt=actual.split(':');chosen=(act,int(amt))
    if chosen not in choices:choices.append(chosen)
    need(len(choices)*len(priors)*max_nodes<=1048576,'Total node budget exceeded')
    envelope={};details=[]
    for name,src,deals in priors:
        r,stats=envelopes(s,s.actor,deals,choices,rake_bps=config['rake_bps'],rake_cap=config['rake_cap'],rake_on_fold=config['rake_on_fold'],max_nodes=max_nodes,rank_worker=rank_worker)
        for k,(x,y) in r.items():envelope[k]=(min(x,envelope[k][0]),max(y,envelope[k][1])) if k in envelope else (x,y)
        details.append(dict(id=name,provenance=src,posterior=[dict(holdings=dict(zip(s.order,hs)),probability=ratio(w)) for hs,w in deals],bounds={k:[ratio(x),ratio(y)] for k,(x,y) in r.items()},stats=stats))
    better=[(x-envelope[actual][1],k,y-envelope[actual][0]) for k,(x,y) in envelope.items() if k!=actual and x>envelope[actual][1]];best=max(better) if better else None
    return dict(status='CONDITIONAL_CONTINUATION_ENVELOPE',prefix_sha256=key,config_sha256=digest(config),actual=actual,legal_action_count=count,action_set_complete=len(choices)==count,action_ev_bounds_exact={k:[ratio(x),ratio(y)] for k,(x,y) in envelope.items()},conditional_dominance=None if best is None else dict(alternative=best[1],gap_bb=[ratio(best[0]),ratio(best[2])]),hypotheses=details,rank_backend='native' if rank_worker is not None else 'python',range_assumptions_verified=False,reconstruction_verified=False,strategy_verified=False,gto_solution=False)


def review(reconstruction,configs,streets=STREETS,*,max_nodes=2048,rank_worker=None):
    need(reconstruction.get('version')=='plo5-auto-reconstruction-candidates-v1' and reconstruction.get('hands_reconstructed') is False and reconstruction.get('strategy_authorized') is False,'Expected candidate reconstruction')
    selected=street_filter(streets);rows=reconstruction['decision_records'];sel=select(rows,selected);need(not sel['errors'] and not sel['adequate_count'] and all(d.get('reconstruction_verified') is False and d.get('strategy_verified') is False for d in rows),'Unexpected certified input')
    hands={h['seed']['hand_id']:h for h in reconstruction['hands']};need(len(hands)==len(reconstruction['hands']) and type(configs) is dict and set(configs)<=set(hands),'Invalid config roster');out=[]
    for d in rows:
        if d['street'] not in selected:continue
        h=hands[d['hand_id']];j=int(d['decision_id']);s,_,actual=prefix(h['seed'],h['events'],j);need(actual==d['action'] and d['street']=={0:'preflop',3:'flop',4:'turn',5:'river'}[len(board(s))],'Decision mismatch');cfg=configs.get(d['hand_id'],{}).get(d['decision_id']);entry=dict(hand_id=d['hand_id'],decision_id=d['decision_id'],street=d['street'],status='NO_DECLARED_CONTINUATION_PRIOR')
        if cfg is not None:
            try:r=evaluate_decision(h['seed'],h['events'],j,cfg,max_nodes=max_nodes,rank_worker=rank_worker)
            except ValueError as exc:entry.update(status='MODEL_UNAVAILABLE',reason=str(exc))
            else:entry.update(status=r['status'],model=r)
        out.append(entry)
    return dict(version='plo5-continuation-review-v1',estimates=out,selection=sel,strategy_verified=False)
