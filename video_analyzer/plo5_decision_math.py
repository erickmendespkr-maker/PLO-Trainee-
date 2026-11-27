"""Offline decision metrics and exact conditional showdown/terminal-call estimates.
Model assumptions and video reconstruction are not independently certified.
"""
from fractions import Fraction
from itertools import combinations, islice
from math import comb
from plo5_pre_gto_context import cards, need
from plo5_post_gto_context import DECK, normalize
from plo5_post_gto_tree import start, step, advance, bounds
from plo5_post_gto_multiway_reach import condition_path
from plo5_post_gto_multiway_ledger import settle
from plo5_strategy_cache import solve_cached, lookup
from plo5_evaluator import evaluate
from plo5_selective_review import select, action_key, model_state, street_filter, STREETS
from plo5_snapshot_replay import replay, reveal
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def ratio(x):return [x.numerator,x.denominator]


def equity(context, result, history, holding, *, joint=None, rank_worker=None, max_runouts=20000):
    """Exact unordered runouts over the conditional joint model, not estimated real ranges."""
    need(type(max_runouts) is int and 1<=max_runouts<=100000,'Invalid runout budget')
    c=normalize(context);s=start(context);h=cards(holding)
    for p,a,v in history:
        if p=='chance':
            need(v==0 and a not in h,'Invalid chance');s=advance(s,a)
        else:s=step(s,p,a,v)
    need(s.pending and not set(h)&set(s.board),'Invalid decision')
    i=s.pending[0];posterior=condition_path(context,result,history,joint=joint,known={s.actor:h},intervene=s.actor)
    out=dict(status=posterior['status'],equity=None,terminal_ev=None,range_assumptions_verified=False,gto_solution=False)
    if posterior['status']!='CONDITIONAL_JOINT_RANGE':return out
    n=len(s.order);missing=5-len(s.board);count=comb(52-5*n-len(s.board),missing);rows=posterior['deals']
    need(count*len(rows)<=max_runouts,'Equity runout budget exceeded')
    mass=sum(Fraction(*d['exact_probability']) for d in rows);need(mass==1,'Invalid posterior mass')
    b=bounds(s);call=b['call_payment'];terminal=None
    # HU only: every legal alternative is fold or call and call closes betting.
    if len(s.order)==2 and call and b['raise_min'] is None:
        child=step(s,s.actor,'call',call)
        if child.status in ('all_in_showdown','river_showdown'):terminal=child
    q=Fraction(0);call_ev=Fraction(0);fold_ev=Fraction(0);wins=Fraction(0);ties=Fraction(0)
    if terminal is not None:
        f=step(s,s.actor,'fold',0);z=settle(f.base_pot,f.total_paid,f.folded,[None]*n,c['rake_bps'],c['rake_cap'],rake_on_fold=result['rake_on_fold'])
        fold_ev=(z['awards'][i]+z['returned'][i])/s.bb
    for d in rows:
        hands=d['holdings'];dead=set(s.board).union(*(set(k) for k in hands));need(len(dead)==len(s.board)+5*n,'Blocker conflict')
        w=Fraction(*d['exact_probability'])/count;deck=sorted(DECK-dead)
        runouts=iter(combinations(deck,missing))
        while True:
            batch=list(islice(runouts,256))
            if not batch:break
            queries=[(hands[j],list(s.board)+list(run)) for run in batch for j in s.active]
            ranks=[(r['rank'],) for r in rank_worker.lookup(5,queries)] if rank_worker is not None else [evaluate(k,board)['rank'] for k,board in queries]
            for t in range(len(batch)):
                rr=[None]*n
                for k,j in enumerate(s.active):rr[j]=ranks[t*len(s.active)+k]
                best=max(rr[j] for j in s.active);victors=[j for j in s.active if rr[j]==best]
                if i in victors:
                    q+=w/len(victors)
                    if len(victors)==1:wins+=w
                    else:ties+=w
                if terminal is not None:
                    z=settle(terminal.base_pot,terminal.total_paid,terminal.folded,rr,c['rake_bps'],c['rake_cap'],rake_on_fold=result['rake_on_fold'])
                    call_ev+=w*(z['awards'][i]+z['returned'][i]-call)/s.bb
    out.update(status='EXACT_CONDITIONAL_MODEL_EQUITY',equity=ratio(q),win_probability=ratio(wins),tie_probability=ratio(ties),joint_deals=len(rows),runouts=count*len(rows),path_probability=posterior['path_probability'],path_probability_scope=posterior['path_probability_scope'],intervened_seat=s.actor,folded_cards_retained=True,scope='equal_eligible_showdown_share_not_realized_equity_or_sidepot_ev',rank_backend='native' if rank_worker is not None else 'python')
    if terminal is not None:out['terminal_ev']=dict(basis='incremental_bb',actions={'fold:0':ratio(fold_ev),action_key(['call',call]):ratio(call_ev)},scope='exact_given_conditional_model_and_rake_not_GTO_certificate')
    return out


def evaluate_model(cache,model,*,cfr_executable=None,rank_worker=None,max_runouts=20000):
    state=model_state(model);c=model['context'];history=model['history'];h=model['holding'];actual=action_key(model['action'])
    opts={k:model[k] for k in ('iterations','pot_bps','rake_on_fold','joint') if k in model}
    data=solve_cached(cache,c,cfr_executable=cfr_executable,**opts);r=data['result'];hit=lookup(data,history,h)
    eq=equity(c,r,history,h,joint=model.get('joint'),rank_worker=rank_worker,max_runouts=max_runouts)
    values={} if hit['status']!='CONDITIONAL_POLICY' else {action_key([a['action'],a['amount']]):a['ev_bb'] for a in hit['policy']['actions']}
    return dict(state=state,actual=actual,policy_ev_bb=values,policy_status=hit['status'],equity=eq,cache_key=data['cache_key'],cache_hit=data['cache_hit'],nashconv_bb=r['nashconv_bb'],backend=r['backend'],strategy_verified=False)


def snapshot_metrics(manifest,seed,snapshots,streets=STREETS):
    """Replay declared snapshots and derive independent metrics at each Hero decision."""
    selected=street_filter(streets);r=replay(manifest,seed,snapshots);mapping=r['positions'];hero=mapping['hero_bottom']
    s=pre.start({p:seed['initial'][k] for k,p in mapping.items()},seed['sb'],seed['bb']);board=[];root=s;rows=[]
    decisions={d['decision_id']:d for d in r['decision_records']}
    for j,e in enumerate(r['events']):
        if 'cards' in e:s=reveal(s,e['cards']);root=s;board+=e['cards'];continue
        engine=pre if isinstance(s,pre.State) else post
        if str(j) in decisions:
            d=decisions[str(j)];need(s.actor==hero and d['action']==action_key([e['action'],e['amount']]),'Decision mismatch')
            if d['street'] in selected:
                i=s.pending[0];b=engine.bounds(s);call=b['call_payment'];opponents=[k for k in s.active if k!=i]
                effective={s.order[k]:min(s.remaining[i],s.remaining[k])/s.bb for k in opponents}
                spr=min(root.remaining)/root.pot if len(root.order)==2 and root.pot else None
                rows.append(dict(hand_id=d['hand_id'],decision_id=d['decision_id'],street=d['street'],position=hero,board=list(board),action=d['action'],pot_bb=s.pot/s.bb,call_bb=call/s.bb,pot_odds_gross=call/(s.pot+call) if call else None,effective_remaining_bb_by_opponent=effective,hu_spr_street_start=spr,ev=None,equity=None,status='UNVERIFIED_SNAPSHOT_PREFIX'))
        s=engine.step(s,e['position'],e['action'],e['amount'])
    return dict(replay_status=r['status'],metrics=rows,selection=select(r['decision_records'],selected),strategy_verified=False)


def review_snapshots(cache,manifest,seed,snapshots,*,ranges,rake_bps,rake_cap,rake_on_fold,
                     streets=STREETS,iterations=100,pot_bps=(),joint=None,cfr_executable=None,rank_worker=None,max_runouts=20000):
    """Anchor one explicit prior at a live, equal-eligibility flop root.
    Derive each subsequent prefix from reconstructed events, retaining the same
    prior and conditioning on observed bets/draws. No preflop EV, no prior folds,
    no guessed ranges or certification. Other snapshots still yield metrics.
    """
    selected=street_filter(streets);base=snapshot_metrics(manifest,seed,snapshots,selected)
    r=replay(manifest,seed,snapshots);mapping=r['positions'];s=pre.start({p:seed['initial'][k] for k,p in mapping.items()},seed['sb'],seed['bb']);root=None;prefix=[];out=[]
    selected_ids={m['decision_id'] for m in base['metrics']}
    for j,e in enumerate(r['events']):
        if 'cards' in e:
            was_pre=isinstance(s,pre.State);s=reveal(s,e['cards'])
            if was_pre:
                if len(s.active)==len(s.order) and all(s.remaining) and len(set(s.total_paid))==1 and s.actor==s.order[0]:
                    root=dict(variant=5,board=list(s.board),seats=list(s.order),actor=s.actor,pot=s.pot,bb=s.bb,stacks=dict(zip(s.order,s.remaining)),ranges=ranges,rake_bps=rake_bps,rake_cap=rake_cap,tree_version=post.VERSION,continuation_version='snapshot-flop-prior-v1')
                    normalize(root)
            elif root is not None:prefix.append(['chance',e['cards'][0],0])
            continue
        engine=pre if isinstance(s,pre.State) else post
        if str(j) in selected_ids:
            if root is None:out.append(dict(decision_id=str(j),status='NO_SUPPORTED_POSTFLOP_ROOT'))
            else:
                m=dict(context=root,history=list(prefix),holding=seed['holding'],action=[e['action'],e['amount']],rake_on_fold=rake_on_fold,iterations=iterations,pot_bps=pot_bps,joint=joint)
                # Strict public replay uses no later cards; unsupported model budgets
                # or histories remain unresolved, without affecting other decisions.
                try:a=evaluate_model(cache,m,cfr_executable=cfr_executable,rank_worker=rank_worker,max_runouts=max_runouts)
                except ValueError as exc:out.append(dict(decision_id=str(j),status='MODEL_UNAVAILABLE',reason=str(exc)))
                else:out.append(dict(decision_id=str(j),status='EXPERIMENTAL_MODEL_ONLY',estimate=a))
        s=engine.step(s,e['position'],e['action'],e['amount'])
        if root is not None:prefix.append([e['position'],e['action'],e['amount']])
    return dict(base,estimates=out,range_provenance='EXPLICIT_DECLARED_FLOP_PRIOR',strategy_verified=False)
