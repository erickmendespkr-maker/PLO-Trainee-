"""Conditional terminal heads-up PLO5 EV, with explicit response and rake models."""
from fractions import Fraction
import hashlib
import json

if __package__:
    from .plo5_equity import equity, prepare
else:
    from plo5_equity import equity, prepare


def integer(value, name, minimum=0, maximum=10**9):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid '+name)
    return value


def fraction_info(q):
    return {'numerator':q.numerator,'denominator':q.denominator}


def analyze(s, *, method='auto', trials=2000, seed=0, max_exact=5000):
    """Amounts are integer chips; EV is incremental from the decision in BB.

    Opponent response probabilities per combo are declared, not inferred.
    Each aggressive action terminates in opponent fold or matched call/showdown.
    No short calls, side pots, reraises, future betting or verified legality.
    """
    fields={'variant','hero','board','range','pot','hero_street','opponent_street',
            'hero_stack','opponent_stack','bb','min_increment','rake_bps',
            'rake_cap','rake_on_fold','aggressions'}
    if type(s) is not dict or set(s)!=fields or type(s['variant']) is not int or s['variant']!=5:
        raise ValueError('Strict PLO5 scenario required')
    p,own,opp,hs,vs,bb,inc,rate,cap=(integer(s[k],k,1 if k in ('pot','hero_stack','bb','min_increment') else 0,
            10000 if k=='rake_bps' else 10**9) for k in ('pot','hero_street','opponent_street','hero_stack','opponent_stack','bb','min_increment','rake_bps','rake_cap'))
    if type(s['rake_on_fold']) is not bool or opp<own or p<own+opp or opp-own>hs:
        raise ValueError('Inconsistent pot, contributions, stack or rake; short call unsupported')
    c=opp-own
    h,b,legal,audit=prepare(s['hero'],s['board'],s['range'])
    if any(e['weight']>100000 for e in s['range']):
        raise ValueError('Base weight exceeds response-model limit')
    actions=s['aggressions']
    if type(actions) is not list or len(actions)>5:
        raise ValueError('Expected up to five aggressive alternatives')
    # Extra over the call. Full matched raises only, under declared minimum and cap.
    max_extra=min(p+c,hs-c,vs)
    seen=set(); validated=[]
    for a in actions:
        if type(a) is not dict or set(a)!={'extra','call_bps'}:
            raise ValueError('Invalid aggression')
        x=integer(a['extra'],'extra',1)
        probs=a['call_bps']
        if not inc<=x<=max_extra or x in seen or type(probs) is not list or len(probs)!=len(s['range']):
            raise ValueError('Invalid sizing, unmatched call, or response list')
        probs=[integer(v,'call probability bps',0,10000) for v in probs]
        validated.append((x,{tuple(sorted(e['cards'])):q for e,q in zip(s['range'],probs)}));seen.add(x)
    def fee(pool):
        return min(cap,pool*rate//10000)
    def solve(entries):
        return equity(h,b,entries,method=method,trials=trials,seed=seed,max_exact=max_exact)
    def q_of(result):
        f=result['equity_fraction'];return Fraction(f['numerator'],f['denominator'])
    def row(kind,extra,point,lo,hi,**meta):
        return {'action':kind,'extra_chips':extra,'ev_bb':float(point/bb),
                'ev_fraction_bb':fraction_info(point/bb),'sampling_interval_bb':[lo/bb,hi/bb],**meta}
    base=solve(s['range']); q=q_of(base); lo,hi=base['sampling_ci95']
    final=p+c; net=final-fee(final)
    rows=[]
    if c:
        rows.append(row('fold',0,Fraction(0),0.,0.))
    rows.append(row('call' if c else 'check',0,q*net-c,lo*net-c,hi*net-c,
                    hero_increment_chips=c,showdown_pot_chips=final,showdown_rake_chips=fee(final),equity=base))
    for x,responses in sorted(validated):
        # Conditional range = prior legal combo mass times call probability.
        called=[{'cards':cards,'weight':w*responses[cards]} for cards,w,_ in legal if responses[cards]]
        call_mass=sum(e['weight'] for e in called)
        call_p=Fraction(call_mass,audit['legal_weight']*10000)
        fold_p=1-call_p
        # Unmatched extra returned; call portion matched. Fold-branch rake base
        # is p+c, only if explicitly enabled. No other rake policy inferred.
        fold_fee=fee(p+c) if s['rake_on_fold'] else 0
        fold_gain=p-fold_fee
        called_pot=p+c+2*x; called_net=called_pot-fee(called_pot)
        r=solve(called) if called else None
        point=fold_p*fold_gain
        low=high=float(point)
        if r is not None:
            point+=call_p*(q_of(r)*called_net-c-x)
            low+=float(call_p)*(r['sampling_ci95'][0]*called_net-c-x)
            high+=float(call_p)*(r['sampling_ci95'][1]*called_net-c-x)
        rows.append(row('raise' if opp else 'bet',x,point,low,high,hero_increment_chips=c+x,
                        opponent_increment_if_called_chips=x,fold_probability=float(fold_p),
                        fold_probability_fraction=fraction_info(fold_p),fold_rake_chips=fold_fee,
                        showdown_pot_chips=called_pot,showdown_rake_chips=fee(called_pot),equity=r))
    return {'variant':5,'status':'conditional_terminal_ev_not_video_verified','baseline':'fold_zero_incremental',
            'scenario_sha256':hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'equity_options':{'method':method,'trials':trials,'seed':seed,'max_exact':max_exact},
            'pot_chips':p,'call_cost_chips':c,'bb_chips':bb,'max_matched_extra_chips':max_extra,
            'break_even_call_equity':float(Fraction(c,net)) if c and net else None,
            'pot_odds_without_rake':float(Fraction(c,final)) if c else None,
            'rake_model':{'bps':rate,'cap_chips':cap,'on_fold':s['rake_on_fold'],'rounding':'floor_to_chip'},
            'actions':rows,'range_audit':audit,'response_model':'declared_per_combo_call_probability_bps',
            'sampling_intervals_are_marginal':True,'range_or_response_uncertainty_included':False,
            'future_betting_modeled':False,'betting_legality_verified':False,'video_verified':False,
            'gto_solution':False,'strategic_error_established':False,'ev_loss_bb':None,
            'automatic_clip_selection_authorized':False}
