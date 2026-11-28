"""Offline local EV bounds for terminal fold/call decisions, under declared joint hypotheses.
Exact rational residual mass bounds, not sampling confidence or real-range certificates.
"""
from fractions import Fraction
from itertools import combinations, islice
from math import comb
import hashlib
import json
from plo5_pre_gto_context import cards, integer, need
from plo5_post_gto_context import DECK
from plo5_post_gto_multiway_ledger import settle
from plo5_evaluator import evaluate
from plo5_snapshot_replay import reveal, positions
from plo5_selective_review import action_key, select, STREETS, street_filter
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def ratio(x):return [x.numerator,x.denominator]


def prefix(seed,events,index):
    need(type(events) is list and type(index) is int and 0<=index<len(events)<=512,'Invalid event index')
    h=cards(seed['holding']);mapping=positions(seed['dealt'],seed['button']);hero=mapping['hero_bottom']
    s=pre.start({p:seed['initial'][k] for k,p in mapping.items()},seed['sb'],seed['bb'])
    board=[]
    for e in events[:index]:
        if 'cards' in e:
            new=e['cards'];need(set(e)=={'cards'} and type(new) is list and all(type(c) is str and c in DECK for c in new) and len(set(h+board+new))==len(h+board+new),'Invalid board prefix')
            s=reveal(s,new);board+=new
        else:
            need(set(e)=={'position','action','amount'},'Invalid action event')
            s=(pre if isinstance(s,pre.State) else post).step(s,e['position'],e['action'],e['amount'])
    e=events[index];need(set(e)=={'position','action','amount'} and s.actor==e['position']==hero,'Not a Hero decision')
    engine=pre if isinstance(s,pre.State) else post
    engine.step(s,hero,e['action'],e['amount'])
    return s,h,action_key([e['action'],e['amount']])


def terminal(s,holding,hypotheses,*,rake_bps,rake_cap,rake_on_fold,max_runouts=4096,rank_worker=None):
    """Joint ranges are explicitly conditioned at this decision, not learned from future cards.
    All dealt players, including folds, must have physical holdings in each joint row.
    The unenumerated mass is bounded by worst/best rank settlement, not extrapolated.
    """
    need(isinstance(s,(pre.State,post.State)) and s.pending,'Expected betting decision')
    h=cards(holding);board=[] if isinstance(s,pre.State) else list(s.board)
    need(not set(h)&set(board),'Hero/board conflict');engine=pre if isinstance(s,pre.State) else post
    b=engine.bounds(s);call=b['call_payment'];i=s.pending[0];n=len(s.order)
    need(type(max_runouts) is int and 0<=max_runouts<=100000,'Invalid enumeration budget')
    need(type(hypotheses) is list and 1<=len(hypotheses)<=16,'Invalid hypothesis roster')
    need(integer(rake_bps)<=10000 and type(rake_on_fold) is bool,'Invalid rake rule');integer(rake_cap)
    if not call or b['raise_min'] is not None:return dict(status='NONTERMINAL_OR_OTHER_LEGAL_ACTIONS',strategy_verified=False)
    child=engine.step(s,s.actor,'call',call)
    if child.status not in ('all_in_showdown','river_showdown'):return dict(status='CALL_DOES_NOT_CLOSE_BETTING',strategy_verified=False)
    paid=child.paid if engine is pre else child.total_paid
    base=0 if engine is pre else child.base_pot
    def payout(ranks):
        z=settle(base,paid,child.folded,ranks,rake_bps,rake_cap,rake_on_fold=rake_on_fold)
        return (z['awards'][i]+z['returned'][i]-call)/s.bb
    # Hero ranked strictly below/above all eligible opponents. Side pots, returned
    # uncalled amounts, fractional splits and rake obey the same ledger in both bounds.
    lo=payout([(0,) if j==i else (1,) for j in range(n)])
    hi=payout([(2,) if j==i else (1,) for j in range(n)])
    results=[];names=set();missing=5-len(board);per=comb(52-5*n-len(board),missing)
    for hyp in hypotheses:
        need(type(hyp) is dict and set(hyp)=={'id','provenance','deals'},'Invalid hypothesis')
        name=hyp['id'];source=hyp['provenance'];need(type(name) is str and 0<len(name)<=128 and name not in names and type(source) is str and 0<len(source)<=1024,'Missing hypothesis provenance');names.add(name)
        deals=hyp['deals'];need(type(deals) is list and 1<=len(deals)<=4096,'Invalid joint range');parsed=[];seen=set()
        for d in deals:
            need(type(d) is dict and set(d)=={'holdings','weight'} and type(d['holdings']) is dict and set(d['holdings'])==set(s.order),'All dealt holdings required')
            hands=tuple(tuple(cards(d['holdings'][p])) for p in s.order);dead=set(board).union(*(set(k) for k in hands));need(list(hands[i])==h and len(dead)==len(board)+5*n and hands not in seen,'Conflicting or duplicate joint deal');seen.add(hands)
            parsed.append((hands,integer(d['weight'],1),sorted(DECK-dead)))
        # Deterministic ordering; bounds remain valid even if the enumeration order is biased.
        parsed.sort();total=sum(w for _,w,_ in parsed);ev=Fraction(0);mass=Fraction(0);done=0
        for hands,w,deck in parsed:
            runouts=iter(islice(combinations(deck,missing),max_runouts-done))
            probability=Fraction(w,total*per)
            while True:
                batch=list(islice(runouts,128))
                if not batch:break
                queries=[(hands[j],board+list(run)) for run in batch for j in child.active]
                ranks=[(r['rank'],) for r in rank_worker.lookup(5,queries)] if rank_worker is not None else [evaluate(k,b)['rank'] for k,b in queries]
                need(len(ranks)==len(queries),'Incomplete rank batch')
                for t in range(len(batch)):
                    rr=[None]*n
                    for k,j in enumerate(child.active):rr[j]=ranks[t*len(child.active)+k]
                    ev+=probability*payout(rr)
                mass+=probability*len(batch);done+=len(batch)
            if done==max_runouts:break
        a=ev+(1-mass)*lo;z=ev+(1-mass)*hi
        results.append(dict(id=name,provenance=source,call_ev_bounds_bb=[ratio(a),ratio(z)],enumerated_mass=ratio(mass),evaluated_runouts=done,total_runouts=per*len(parsed),exact=mass==1))
    lower=min(Fraction(*r['call_ev_bounds_bb'][0]) for r in results);upper=max(Fraction(*r['call_ev_bounds_bb'][1]) for r in results)
    # Folding while facing a legal bet costs zero additional chips; sunk chips do
    # not enter incremental EV. Under the ledger rules a folded player cannot win.
    return dict(status='CONDITIONAL_TERMINAL_BOUNDS',action_set_complete=True,action_ev_bounds_exact={'fold:0':[[0,1],[0,1]],action_key(['call',call]):[ratio(lower),ratio(upper)]},conditional_preference='CALL' if lower>0 else 'FOLD' if upper<0 else 'TIED' if lower==upper==0 else 'UNRESOLVED',pot_odds_gross=ratio(Fraction(call,s.pot+call)),hypotheses=results,rank_backend='native' if rank_worker is not None else 'python',range_assumptions_verified=False,reconstruction_verified=False,strategy_verified=False,gto_solution=False)


def review(reconstruction,configs,streets=STREETS,*,rank_worker=None,max_runouts=4096):
    """Macro25 candidate input; never promotes conditional bounds to reportable errors."""
    need(reconstruction.get('version')=='plo5-auto-reconstruction-candidates-v1' and reconstruction.get('hands_reconstructed') is False and reconstruction.get('strategy_authorized') is False,'Expected candidate reconstruction')
    chosen=street_filter(streets);rows=reconstruction['decision_records'];hands=reconstruction['hands'];need(type(hands) is list and len(hands)<=512,'Invalid hand roster')
    index={h['seed']['hand_id']:h for h in hands};need(len(index)==len(hands),'Duplicate hand')
    selection=select(rows,chosen);need(not selection['errors'] and selection['adequate_count']==0 and all(d.get('reconstruction_verified') is False and d.get('strategy_verified') is False for d in rows),'Unexpected certified input')
    need(type(configs) is dict and set(configs)<=set(index),'Unknown hand config');out=[]
    for d in rows:
        if d['street'] not in chosen:continue
        h=index[d['hand_id']];j=int(d['decision_id']);s,holding,actual=prefix(h['seed'],h['events'],j)
        street='preflop' if isinstance(s,pre.State) else {3:'flop',4:'turn',5:'river'}[len(s.board)]
        need(actual==d['action'] and street==d['street'],'Decision prefix mismatch')
        cfg=configs.get(d['hand_id'],{}).get(d['decision_id']);entry=dict(hand_id=d['hand_id'],decision_id=d['decision_id'],street=street,actual=actual,pot_bb=ratio(Fraction(s.pot,s.bb)),board=[] if isinstance(s,pre.State) else list(s.board),position=s.actor,status='NO_DECLARED_DECISION_RANGES')
        if cfg is not None:
            need(type(cfg) is dict and set(cfg)=={'hypotheses','rake_bps','rake_cap','rake_on_fold'},'Invalid decision config')
            entry['model']=terminal(s,holding,rank_worker=rank_worker,max_runouts=max_runouts,**cfg);entry['status']=entry['model']['status']
            entry['config_sha256']=hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        out.append(entry)
    return dict(version='plo5-conditional-terminal-review-v1',estimates=out,selection=selection,strategy_verified=False)


def main(argv=None):
    import argparse
    from pathlib import Path
    from contextlib import ExitStack
    from plo5_error_prints import read
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reconstruction');p.add_argument('configs');p.add_argument('output');p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--max-runouts',type=int,default=4096);p.add_argument('--rank');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required');r=read(a.reconstruction);r=r.get('reconstruction',r);cfg=read(a.configs)
    with ExitStack() as stack:
        worker=None
        if a.rank:
            from plo5_rank_worker import RankWorker
            from plo5_rank_lru import CachedRankWorker
            worker=CachedRankWorker(stack.enter_context(RankWorker(a.rank)))
        result=review(r,cfg,a.streets,rank_worker=worker,max_runouts=a.max_runouts)
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2)
    return 0

if __name__=='__main__':raise SystemExit(main())
