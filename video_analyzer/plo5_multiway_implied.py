"""Offline PLO5 multiway showdown shares and conditional future-transfer EV."""
from bisect import bisect_right
from fractions import Fraction
from itertools import accumulate, combinations, product
from math import comb, log, prod, sqrt
import random

from plo5_action_ev import integer, fraction_info
from plo5_equity import DECK, prepare
from plo5_evaluator import evaluate


def need(ok, message):
    if not ok:
        raise ValueError(message)


def multiway(hero, board, ranges, *, method='auto', trials=2000, seed=0, max_exact=5000):
    """1–5 opponents, independent prior weights conditioned on disjoint cards."""
    need(type(ranges) is list and 1<=len(ranges)<=5,'Expected 1–5 opponent ranges')
    need(method in ('auto','exact','monte_carlo'),'Invalid method')
    integer(trials,'trials',1,100000); integer(seed,'seed',0,2**32-1)
    integer(max_exact,'exact budget',1,20000)
    legal=[]; audits=[]; masks={c:1<<i for i,c in enumerate(DECK)}
    for entries in ranges:
        h,b,rows,audit=prepare(hero,board,entries)
        legal.append([(cards,w,sum(masks[c] for c in cards)) for cards,w,_ in rows]); audits.append(audit)
    candidates=prod(map(len,legal))
    need(candidates<=20000,'Joint range candidate budget exceeded')
    states=[]; total=0
    for group in product(*legal):
        used=0; weight=1; hands=[]
        for cards,w,mask in group:
            if used&mask: break
            used|=mask; weight*=w; hands.append(cards)
        else:
            states.append((tuple(hands),weight)); total+=weight
    need(total>0,'No compatible joint holdings')
    n=1+len(ranges); k=5-len(b); runouts=comb(52-5*n-len(b),k)
    possible=len(states)*runouts
    exact=method=='exact' or (method=='auto' and possible<=max_exact)
    need(not exact or possible<=max_exact,'Exact enumeration exceeds budget')
    # Bucket 0 = loss, 1 = sole win, j>=2 = split among j winners.
    mass=[0]*(n+1)
    def remaining(hands):
        used=set(h+b).union(*hands)
        return [c for c in DECK if c not in used]
    def outcome(hands,extra):
        full=b+tuple(extra); ranks=[evaluate(x,full)['rank'] for x in (h,)+hands]
        best=max(ranks)
        return ranks.count(best) if ranks[0]==best else 0
    if exact:
        for hands,w in states:
            for extra in combinations(remaining(hands),k): mass[outcome(hands,extra)]+=w
        den=total*runouts
    else:
        rng=random.Random(seed); cum=list(accumulate(w for _,w in states))
        for _ in range(trials):
            hands,_=states[bisect_right(cum,rng.randrange(total))]
            mass[outcome(hands,rng.sample(remaining(hands),k))]+=1
        den=trials
    assert sum(mass)==den
    q=sum((Fraction(mass[j],den*j) for j in range(1,n+1)),Fraction(0)); point=float(q)
    radius=0 if exact else sqrt(log(40)/(2*trials))
    return {'variant':5,'players':n,'method':'exact' if exact else 'monte_carlo',
            'equity':point,'equity_fraction':fraction_info(q),'sampling_ci95':[max(0,point-radius),min(1,point+radius)],
            'share_mass':mass,'mass_denominator':den,'mass_semantics':'weighted_states' if exact else 'sample_counts',
            'sole_win_probability':mass[1]/den,'split_probability':sum(mass[2:])/den,'loss_probability':mass[0]/den,
            'possible_states':possible,'evaluated_states':possible if exact else trials,'seed':None if exact else seed,
            'runouts_per_joint_holding':runouts,'joint_candidates':candidates,'legal_joint_holdings':len(states),
            'input_joint_weight':prod(a['input_weight'] for a in audits),'legal_joint_weight':total,
            'excluded_joint_weight':prod(a['input_weight'] for a in audits)-total,
            'individual_range_audits':audits,'scope':'one_common_eligible_pot_no_side_pots',
            'joint_model':'product_weights_conditioned_on_disjoint_cards','range_uncertainty_included':False,
            'gto_solution':False,'video_verified':False,'future_betting_modeled':False}


def analyze(s, **options):
    """Call versus fold; conditional expected future matched contributions, not a tree.

    All opponents already matched the current wager; pot includes their payments.
    Future chips per player depend on eventual Hero share bucket, by assumption.
    No future folds, unequal contributions, side pots or uncalled bets.
    """
    fields={'variant','hero','board','ranges','pot_chips','call_chips','hero_stack_chips',
            'opponent_stacks_chips','bb_chips','rake_bps','rake_cap_chips','scenarios'}
    need(type(s) is dict and set(s)==fields and type(s['variant']) is int and s['variant']==5,'Strict PLO5 implied-odds scenario required')
    need(type(s['board']) is list and len(s['board']) in (3,4,5),'Postflop board required')
    need(type(s['ranges']) is list and 1<=len(s['ranges'])<=5,'Expected 1–5 ranges')
    n=1+len(s['ranges']); p=integer(s['pot_chips'],'pot',1); c=integer(s['call_chips'],'call',1)
    h=integer(s['hero_stack_chips'],'hero stack',1); bb=integer(s['bb_chips'],'bb',1)
    rate=integer(s['rake_bps'],'rake bps',0,10000); cap=integer(s['rake_cap_chips'],'rake cap')
    stacks=s['opponent_stacks_chips']
    need(type(stacks) is list and len(stacks)==n-1 and c<=min(h,p),'Invalid stacks/call')
    limit=min([h-c]+[integer(x,'opponent remaining stack') for x in stacks])
    if len(s['board'])==5: limit=0
    scenarios=s['scenarios']
    need(type(scenarios) is dict and 1<=len(scenarios)<=5 and all(type(k) is str and 0<len(k.strip())<=80 for k in scenarios),'Expected 1–5 named scenarios')
    for amounts in scenarios.values():
        need(type(amounts) is list and len(amounts)==n+1,'Expected contribution per share bucket')
        for x in amounts: integer(x,'future matched payment',0,limit)
    eq=multiway(s['hero'],s['board'],s['ranges'],**options)
    mass=eq['share_mass']; den=eq['mass_denominator']; pool=p+c
    def fee(x):return min(cap,x*rate//10000)
    net=pool-fee(pool)
    q=Fraction(**eq['equity_fraction']); base=q*net-c
    out={}
    for name,amounts in scenarios.items():
        payoffs=[]; deltas=[]
        for j,x in enumerate(amounts):
            share=Fraction(1,j) if j else Fraction(0)
            final=pool+n*x
            delta=share*(n*x-(fee(final)-fee(pool)))-x
            deltas.append(delta);payoffs.append(share*net-c+delta)
        gain=sum((Fraction(m,den)*max(0,d) for m,d in zip(mass,deltas)),Fraction(0))
        loss=sum((Fraction(m,den)*max(0,-d) for m,d in zip(mass,deltas)),Fraction(0))
        value=base+gain-loss
        # Bound the full correlated payoff, not independent equity and future gains.
        radius=0 if eq['method']=='exact' else float(max(payoffs)-min(payoffs))*sqrt(log(40)/(2*den))
        point=float(value/bb)
        lo=min(point,max(float(min(payoffs)/bb),point-radius/bb))
        hi=max(point,min(float(max(payoffs)/bb),point+radius/bb))
        out[name]={'future_payment_by_share_bucket_chips':amounts,'ev_call_bb':float(value/bb),
                   'ev_call_fraction_bb':fraction_info(value/bb),'ev_fold_bb':0,
                   'expected_implied_gain_bb':float(gain/bb),'expected_reverse_implied_loss_bb':float(loss/bb),
                   'expected_net_future_delta_bb':float((gain-loss)/bb),'sampling_ci95_bb':[lo,hi],
                   'conditional_call_vs_fold':'POSITIVE' if lo>0 else 'NEGATIVE' if hi<0 else 'TIE' if eq['method']=='exact' and value==0 else 'UNCERTAIN'}
    values=[r['ev_call_bb'] for r in out.values()]
    return {'variant':5,'status':'CONDITIONAL_IMPLIED_ODDS_MODEL','equity_model':eq,
            'base_call_ev_bb':float(base/bb),'base_call_ev_fraction_bb':fraction_info(base/bb),
            'pot_odds_without_rake':float(Fraction(c,pool)),
            'terminal_break_even_equity':float(Fraction(c,net)) if net else None,
            'required_additional_net_future_gain_bb':float(max(Fraction(0),-base)/bb),
            'max_future_matched_payment_per_player_chips':limit,'scenarios':out,
            'ev_call_span_bb':[min(values),max(values)],'span_is_confidence_interval':False,
            'sampling_joint_coverage_lower_bound':1 if eq['method']=='exact' else max(0,1-.05*len(out)),
            'future_model':'outcome_conditioned_equal_matched_payments_no_future_folds',
            'rake_model':{'bps':rate,'cap_chips':cap,'rounding':'floor_to_chip'},
            'current_pot_common_eligibility_and_matched_opponents_declared_only':True,
            'future_betting_tree_modeled':False,'range_or_future_model_uncertainty_included':False,
            'frequency':None,'ev_loss_bb':None,'financial_result_bb':None,'gto_solution':False,
            'video_verified':False,'strategic_error_established':False,'automatic_clip_selection_authorized':False}
