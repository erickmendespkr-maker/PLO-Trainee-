"""Offline PLO5 heads-up preflop 4-bet/stack-off with explicit terminal assumptions."""
from fractions import Fraction
import hashlib
import json

from plo5_action_ev import integer, fraction_info
from plo5_equity import equity, prepare
from plo5_ev_comparison import summarize
from plo5_hand_structure import describe


def need(ok, message):
    if not ok:
        raise ValueError(message)


def analyze(s, *, method='auto', trials=2000, seed=0, max_exact=5000):
    """Two dealt-in players, standard blinds, incremental payments in chips.

    Raise alternatives end in fold or call/showdown; no future betting tree.
    A short all-in raise does not reopen betting against an all-in opponent.
    """
    fields={'variant','hero','position','stacks','sb','bb','history','chosen','range',
            'range_kind','raises','rake_bps','rake_cap','rake_on_fold'}
    need(type(s) is dict and set(s)==fields and type(s['variant']) is int and s['variant']==5,'Strict PLO5 scenario required')
    h=s['hero']; structure=describe(h); hero=s['position']
    need(hero in ('SB','BB') and type(s['stacks']) is dict and set(s['stacks'])=={'SB','BB'},'Originally heads-up table required')
    other='BB' if hero=='SB' else 'SB'
    sb=integer(s['sb'],'sb',1); bb=integer(s['bb'],'bb',1)
    initial={p:integer(s['stacks'][p],'initial stack',1) for p in ('SB','BB')}
    rate=integer(s['rake_bps'],'rake bps',0,10000); cap=integer(s['rake_cap'],'rake cap')
    need(sb<bb and initial['SB']>sb and initial['BB']>bb and type(s['rake_on_fold']) is bool,'Unsupported blinds or rake')
    paid={'SB':sb,'BB':bb}; stack={p:initial[p]-paid[p] for p in paid}
    pending=['SB','BB']; minimum=bb; raise_count=0

    def bounds(p):
        q='BB' if p=='SB' else 'SB'
        c=max(0,paid[q]-paid[p]); pot=sum(paid.values())
        return c,min(stack[p],pot+2*c)

    def validate(p,a,amount):
        q='BB' if p=='SB' else 'SB'; c,maximum=bounds(p)
        integer(amount,'payment')
        need(stack[p]>0,'Actor already all-in')
        need((a=='fold' and c>0 and amount==0) or (a=='check' and c==0 and amount==0 and stack[q]>0)
             or (a=='call' and c>0 and amount==min(c,stack[p]))
             or (a=='raise' and stack[q]>0 and c<amount<=maximum and (amount-c>=minimum or amount==stack[p])),
             'Illegal or unsupported action')
        return c

    need(type(s['history']) is list and len(s['history'])<=100,'Invalid history')
    for e in s['history']:
        need(type(e) is dict and set(e)=={'position','action','amount'} and pending and e['position']==pending[0],'Out-of-order or completed history')
        p=pending.pop(0); q='BB' if p=='SB' else 'SB'; a=e['action']; amount=e['amount']; c=validate(p,a,amount)
        paid[p]+=amount; stack[p]-=amount
        if a=='fold': pending=[]
        elif a=='raise':
            raise_count+=1; minimum=max(minimum,amount-c); pending=[q]
        elif stack[p]==0 or stack[q]==0: pending=[]
    need(pending and pending[0]==hero,'No decision for Hero')
    chosen=s['chosen']; need(type(chosen) is dict and set(chosen)=={'action','amount'},'Explicit chosen action required')
    c,maximum=bounds(hero); validate(hero,chosen['action'],chosen['amount'])
    pot=sum(paid.values()); hs=stack[hero]; vs=stack[other]
    _,_,legal,audit=prepare(h,[],s['range'])
    need(s['range_kind'] in ('explicit','AAxxx_at_least_two'),'Unknown range kind')
    need(all(e['weight']<=100000 for e in s['range']),'Base weight exceeds response-model limit')
    if s['range_kind']=='AAxxx_at_least_two':
        need(all(sum(card[0]=='A' for card in e['cards'])>=2 for e in s['range']),'Non-AAxxx holding in declared AA range')
    need(type(s['raises']) is list and len(s['raises'])<=5,'Up to five raise alternatives')
    alternatives={}
    for a in s['raises']:
        need(type(a) is dict and set(a)=={'amount','call_bps'},'Invalid raise model')
        x=a['amount']; validate(hero,'raise',x)
        probs=a['call_bps']; need(x not in alternatives and type(probs) is list and len(probs)==len(s['range']),'Duplicate sizing or response length mismatch')
        alternatives[x]={tuple(sorted(e['cards'])):integer(q,'call probability bps',0,10000) for e,q in zip(s['range'],probs)}

    def fee(pool): return min(cap,pool*rate//10000)
    def solve(entries): return equity(h,[],entries,method=method,trials=trials,seed=seed,max_exact=max_exact)
    def q_of(r):
        f=r['equity_fraction']; return Fraction(f['numerator'],f['denominator'])
    def row(kind,extra,point,lo,hi,**meta):
        return {'action':kind,'extra_chips':extra,'ev_bb':float(point/bb),
                'ev_fraction_bb':fraction_info(point/bb),'sampling_interval_bb':[lo/bb,hi/bb],**meta}
    def settlement(payment,opponent_payment):
        own=paid[hero]+payment; opp=paid[other]+opponent_payment; matched=min(own,opp)
        return {'hero_payment_chips':payment,'opponent_payment_chips':opponent_payment,
                'hero_return_chips':own-matched,'opponent_return_chips':opp-matched,
                'contested_pot_chips':2*matched,'rake_chips':fee(2*matched),
                'terminal_by_stack':payment==hs or opponent_payment==vs}

    base=solve(s['range']); rows=[]
    if c: rows.append(row('fold',0,Fraction(0),0.,0.))
    call=min(c,hs); settle=settlement(call,0)
    net=settle['contested_pot_chips']-settle['rake_chips']; cost=call-settle['hero_return_chips']
    lo,hi=base['sampling_ci95']
    rows.append(row('call' if c else 'check',0,q_of(base)*net-cost,lo*net-cost,hi*net-cost,
                    settlement=settle,equity=base))
    for payment,response in sorted(alternatives.items()):
        extra=payment-c; op_pay=min(extra,vs); st=settlement(payment,op_pay)
        called=[{'cards':cards,'weight':w*response[cards]} for cards,w,_ in legal if response[cards]]
        cp=Fraction(sum(x['weight'] for x in called),audit['legal_weight']*10000); fp=1-cp
        # On fold all hero excess above opponent's previous contribution returns.
        fold_rake=fee(2*paid[other]) if s['rake_on_fold'] else 0
        fold_gain=pot-fold_rake
        value=fp*fold_gain; low=high=float(value); eq=None
        if called:
            eq=solve(called); net_called=st['contested_pot_chips']-st['rake_chips']; cost_called=payment-st['hero_return_chips']
            value+=cp*(q_of(eq)*net_called-cost_called)
            low+=float(cp)*(eq['sampling_ci95'][0]*net_called-cost_called)
            high+=float(cp)*(eq['sampling_ci95'][1]*net_called-cost_called)
        rows.append(row('raise',extra,value,low,high,settlement=st,equity=eq,
                        fold_probability_fraction=fraction_info(fp),fold_rake_chips=fold_rake,
                        fold_gain_chips=fold_gain,fold_hero_return_chips=paid[hero]+payment-paid[other]))
    digest=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    selected=(chosen['action'],chosen['amount']-c if chosen['action']=='raise' else 0)
    comparison=summarize({'actions':rows,'scenario_sha256':digest},selected)
    return {'variant':5,'status':'CONDITIONAL_TERMINAL_PREFLOP_MODEL','scenario_sha256':digest,
            'position':hero,'raise_count_before':raise_count,'chosen_raise_number':raise_count+2 if chosen['action']=='raise' else None,
            'chosen_all_in':chosen['amount']==hs,'opponent_already_all_in':vs==0,
            'initial_effective_stack_bb':min(initial.values())/bb,'remaining_stacks_chips':stack,
            'contributions_chips':paid,'pot_chips':pot,'to_call_chips':c,'actual_call_payment_chips':call,
            'pot_limit_payment_cap_chips':maximum,'min_full_raise_increment_chips':minimum,
            'terminal_call_equity_required':float(Fraction(cost,net)) if c and net else None,
            'range_kind':s['range_kind'],'range_audit':audit,'base_equity':base,'hand_structure':structure,
            'actions':rows,'comparison':comparison,'sampling_joint_coverage_lower_bound':max(0,1-.05*comparison['stochastic_action_intervals']),
            'history_complete_by_declaration_only':True,'future_betting_modeled':False,
            'rake_model':{'bps':rate,'cap_chips':cap,'on_fold':s['rake_on_fold'],'rounding':'floor_to_chip'},
            'frequency':None,'ev_loss_bb':None,'financial_result_bb':None,'gto_solution':False,
            'video_verified':False,'strategic_error_established':False,'automatic_clip_selection_authorized':False}
