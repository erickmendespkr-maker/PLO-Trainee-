"""Offline PLO5 preflop decision replay from explicitly transcribed action history."""
from fractions import Fraction
from collections import deque
import argparse
import hashlib
import json
from pathlib import Path

from strategic_normalize import POSITIONS
from plo5_hand_structure import describe
from plo5_ev_comparison import compare
from plo5_action_ev import integer


def need(ok, message):
    if not ok:
        raise ValueError(message)


def analyze(s, **options):
    """Standard two-blind cash game, no antes/straddles/short raises/all-ins.

    Contributions are incremental integer chips, history is complete by declaration.
    Never infer RFI from an isolated raise label, or frequencies from equity.
    """
    fields={'variant','hero','position','stacks','sb','bb','history','chosen',
            'rake_bps','rake_cap','rake_on_fold','hypotheses'}
    need(type(s) is dict and set(s)==fields and type(s['variant']) is int and s['variant']==5,'Strict PLO5 preflop schema required')
    structure=describe(s['hero'])
    initial=s['stacks']; hero=s['position']
    need(type(initial) is dict and len(initial) in POSITIONS,'Expected 2–6 dealt-in positions')
    order=POSITIONS[len(initial)]
    need(set(initial)==set(order) and hero in initial,'Position/stacks mismatch')
    stacks={p:integer(initial[p],'initial stack',1) for p in order}
    bb=integer(s['bb'],'bb',1); sb=integer(s['sb'],'sb',1)
    rate=integer(s['rake_bps'],'rake bps',0,10000); cap=integer(s['rake_cap'],'rake cap')
    need(sb<bb and type(s['rake_on_fold']) is bool and stacks['SB']>sb and stacks['BB']>bb,'Unsupported blinds or all-in blind')
    paid={p:sb if p=='SB' else bb if p=='BB' else 0 for p in order}
    for p in order: stacks[p]-=paid[p]
    active=set(order); pending=deque(order); highest=bb; minimum=bb
    raises=[]; limpers=[]; callers=[]; acted=set()

    def bounds(p):
        cost=highest-paid[p]; pot=sum(paid.values())
        return cost,pot,min(stacks[p],pot+2*cost)

    def validate(p,a,amount):
        c,pot,maximum=bounds(p)
        integer(amount,'incremental chips')
        # Deliberately exclude all-ins even when full-sized; next block extends them.
        need(amount<stacks[p],'All-in or short call unsupported')
        need((a=='fold' and amount==0 and c>0) or (a=='check' and amount==0 and c==0)
             or (a=='call' and amount==c and c>0)
             or (a=='raise' and c+minimum<=amount<=maximum and len(active)>1),
             'Illegal or unsupported preflop action')
        return c

    history=s['history']; need(type(history) is list and len(history)<=100,'Invalid bounded history')
    for e in history:
        need(type(e) is dict and set(e)=={'position','action','amount'} and pending and len(active)>1 and e['position']==pending[0],'Incomplete or out-of-order history')
        p=pending.popleft(); a=e['action']; amount=e['amount']; c=validate(p,a,amount)
        paid[p]+=amount; stacks[p]-=amount; acted.add(p)
        if a=='fold': active.remove(p)
        elif a=='call':
            if not raises: limpers.append(p)
            else: callers.append(p)
        elif a=='raise':
            minimum=amount-c; highest=paid[p]; raises.append(p); callers=[]
            i=order.index(p); pending=deque(x for x in order[i+1:]+order[:i] if x in active)
    need(len(active)>1 and pending and pending[0]==hero,'No decision for declared Hero at end of history')
    c,pot,maximum=bounds(hero)
    chosen=s['chosen'];need(type(chosen) is dict and set(chosen)=={'action','amount'},'Explicit chosen action required')
    a=chosen['action']; amount=chosen['amount']; validate(hero,a,amount)
    nr=len(raises); first=hero not in acted
    spot=('facing_4bet_plus' if nr>=3 else 'facing_3bet' if nr==2 else 'facing_open' if nr==1
          else 'limped_pot' if limpers else 'unopened')
    if not nr and c==0: spot='bb_option'
    label=a
    if a=='raise':
        label=('four_bet_plus' if nr>=2 else ('squeeze' if callers else 'three_bet') if nr==1
               else 'isolation_raise' if limpers else 'rfi' if first else 'first_raise_after_hero_action')
    elif a=='call':
        label=('limp' if not nr else 'call_after_prior_action' if not first else
               'blind_call' if hero in ('SB','BB') else 'cold_call')
    opponents=[p for p in order if p in active and p!=hero]
    post_order=('BB','SB') if len(order)==2 else ('SB','BB')+tuple(p for p in order if p not in ('SB','BB'))
    in_position=[p for p in opponents if post_order.index(p)<post_order.index(hero)]
    net=pot+c-min(cap,(pot+c)*rate//10000)
    report={'variant':5,'status':'DESCRIPTIVE_PREFLOP_CONTEXT','position':hero,'players_dealt':len(order),
            'active_opponents':opponents,'pending_after_hero':list(pending)[1:],
            'opponents_hero_has_postflop_position_on':in_position,'spot':spot,'chosen_class':label,
            'first_hero_action':first,'rfi_opportunity':first and not raises and not limpers and c>0 and min(maximum,stacks[hero]-1)>=c+minimum,
            'blind_defense_context':hero in ('SB','BB') and nr>0 and c>0,
            'raise_count_before':nr,'limpers_before':limpers,'callers_since_last_raise':callers,
            'last_raiser':raises[-1] if raises else None,'pot_chips':pot,'to_call_chips':c,
            'remaining_stacks_chips':stacks,'street_contributions_chips':paid,'bb_chips':bb,
            'effective_initial_stack_bb':{p:float(Fraction(min(initial[hero],initial[p]),bb)) for p in opponents},
            'effective_remaining_stack_bb':{p:float(Fraction(min(stacks[hero],stacks[p]),bb)) for p in opponents},
            'min_full_raise_increment_chips':minimum,'pot_limit_payment_cap_chips':maximum,
            'max_non_all_in_raise_payment_chips':min(maximum,stacks[hero]-1) if min(maximum,stacks[hero]-1)>=c+minimum else None,
            'pot_odds_without_rake':float(Fraction(c,pot+c)) if c else None,
            'terminal_call_equity_with_rake':float(Fraction(c,net)) if c and net else None,
            'rake_model':{'bps':rate,'cap_chips':cap,'on_fold':s['rake_on_fold'],'rounding':'floor_to_chip'},
            'hand_structure':structure,'chosen_declared':chosen,'history_sha256':hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'frequency':None,'ev_bb':None,'ev_loss_bb':None,'gto_solution':False,'video_verified':False,
            'strategic_error_established':False,'automatic_clip_selection_authorized':False,
            'betting_legality_verified':False,'financial_result_bb':None,'variance_attribution':None,
            'history_complete_by_declaration_only':True,'conditional_model':None}
    hypotheses=s['hypotheses'];need(type(hypotheses) is dict,'Invalid hypotheses')
    if not hypotheses:
        report['model_status']='NO_MATCH'
    elif len(order)!=2:
        report['model_status']='UNSUPPORTED_MULTIPLAYER_CONTEXT'
    else:
        opp=opponents[0]
        expected={'variant':5,'board':[],'pot':pot,'hero_street':paid[hero],'opponent_street':paid[opp],
                  'hero_stack':stacks[hero],'opponent_stack':stacks[opp],'bb':bb,'min_increment':minimum,
                  'rake_bps':rate,'rake_cap':cap,'rake_on_fold':s['rake_on_fold']}
        for model in hypotheses.values():
            need(type(model) is dict and all(model.get(k)==v for k,v in expected.items()) and sorted(model.get('hero',[]))==sorted(s['hero']),'Conditional model context mismatch')
            # Keep model action space within this non-all-in replay scope.
            need(all(x['extra']+c<stacks[hero] and x['extra']<stacks[opp] for x in model['aggressions']),'All-in model alternative unsupported')
        result=compare(hypotheses,{'action':a,'extra_chips':amount-c if a=='raise' else 0},**options)
        report['conditional_model']=result
        report['model_status']='CONDITIONAL_MODEL_ONLY' if result['coverage']['hypotheses_comparable'] else 'NO_MATCH' if result['coverage']['no_match'] else 'INSUFFICIENT_DATA'
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario');parser.add_argument('output');args=parser.parse_args(argv)
    source=Path(args.scenario);out=Path(args.output)
    need(source.is_file() and not source.is_symlink() and 0<source.stat().st_size<=8*1024*1024,'Unsafe input')
    need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    def unique(items):
        d={}
        for k,v in items:
            need(k not in d,'Duplicate JSON key');d[k]=v
        return d
    raw=source.read_bytes();need(len(raw)<=8*1024*1024,'Oversized input')
    result=analyze(json.loads(raw,object_pairs_hook=unique))
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':raise SystemExit(main())
