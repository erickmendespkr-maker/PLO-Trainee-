"""Offline PLO5 conditional action comparison; never a verified strategic grade."""
from fractions import Fraction
import math

if __package__:
    from .plo5_action_ev import analyze, fraction_info
else:
    from plo5_action_ev import analyze, fraction_info


def action_key(action):
    if type(action) is not dict or set(action) != {'action','extra_chips'}:
        raise ValueError('Explicit action and sizing required')
    kind,x=action['action'],action['extra_chips']
    if kind not in ('fold','check','call','bet','raise') or type(x) is not int or not 0<=x<=10**9:
        raise ValueError('Invalid action key')
    if (kind in ('bet','raise')) != (x>0):
        raise ValueError('Aggressive action requires exact extra above call')
    return kind,x


def label(key):
    return {'action':key[0],'extra_chips':key[1]}


def context_key(s):
    """Only the range and response assumptions may vary across hypotheses."""
    return (tuple(sorted(s['hero'])),tuple(s['board']),
            tuple(s[k] for k in ('variant','pot','hero_street','opponent_street','hero_stack',
                                 'opponent_stack','bb','min_increment','rake_bps','rake_cap','rake_on_fold')),
            tuple(sorted(a['extra'] for a in s['aggressions'])))


def summarize(report, chosen):
    rows={action_key(label((a['action'],a['extra_chips']))):a for a in report['actions']}
    points={}; bounds={}; stochastic=0
    for key,a in rows.items():
        f=a['ev_fraction_bb']; point=Fraction(f['numerator'],f['denominator'])
        points[key]=point
        equity=a.get('equity')
        if equity is not None and equity['method']=='weighted_monte_carlo':
            stochastic+=1
            lo,hi=a['sampling_interval_bb']
            # Preserve exact point and round the float endpoints outward.
            bounds[key]=(min(point,Fraction(math.nextafter(lo,-math.inf))),
                         max(point,Fraction(math.nextafter(hi,math.inf))))
        else:
            bounds[key]=(point,point)
    best=max(points.values()); best_keys=[k for k in points if points[k]==best]
    best_lower=max(lo for lo,_ in bounds.values())
    possible=[k for k,(_,hi) in bounds.items() if hi>=best_lower]
    ranked=[{'action':label(k),'ev_bb':float(points[k]),'ev_fraction_bb':fraction_info(points[k]),
             'sampling_interval_bb':[float(v) for v in bounds[k]],
             'showdown_equity':{field:rows[k]['equity'][field] for field in
                 ('method','equity_fraction','outcome_mass','mass_denominator','sampling_ci95','evaluated_states','seed')}
                 if rows[k].get('equity') is not None else None} for k in sorted(points,key=lambda k:(-points[k],k))]
    common={'scenario_sha256':report['scenario_sha256'],'alternatives':ranked,
            'point_best_actions':[label(k) for k in best_keys],
            'possible_best_actions_under_bounds':[label(k) for k in possible],
            'modeled_actions':len(rows),'stochastic_action_intervals':stochastic,
            'full_action_space_covered':False}
    if chosen not in rows:
        return {**common,'status':'NO_MATCH','conditional_ev_loss_bb':None,
                'conditional_ev_loss_fraction_bb':None,'loss_bounds_bb':None}
    rivals=[k for k in rows if k!=chosen]
    if not rivals:
        return {**common,'status':'INSUFFICIENT_DATA','conditional_ev_loss_bb':None,
                'conditional_ev_loss_fraction_bb':None,'loss_bounds_bb':None}
    point=best-points[chosen]; own_lo,own_hi=bounds[chosen]
    low=max(Fraction(0),max(bounds[k][0]-own_hi for k in rivals))
    high=max(Fraction(0),max(bounds[k][1]-own_lo for k in rivals))
    status=('INFERIOR_UNDER_BOUNDS' if low>0 else
            'BEST_OR_TIED_UNDER_BOUNDS' if high==0 else 'UNCERTAIN_UNDER_BOUNDS')
    return {**common,'status':status,'conditional_ev_loss_bb':float(point),
            'conditional_ev_loss_fraction_bb':fraction_info(point),'loss_bounds_bb':[float(low),float(high)]}


def compare(scenarios, chosen_action, **options):
    """Recompute one decision under 1–5 explicit hypotheses; no imported EV rows."""
    chosen=action_key(chosen_action)
    if type(scenarios) is not dict or not 1<=len(scenarios)<=5 or any(type(k) is not str or not k.strip() or len(k)>80 for k in scenarios):
        raise ValueError('Expected 1–5 named hypotheses')
    output={}; common=None
    for name,s in scenarios.items():
        report=analyze(s,**options)
        key=context_key(s)
        if common is None: common=key
        elif common!=key: raise ValueError('Incompatible decision context or sizing set')
        output[name]=summarize(report,chosen)
    covered=[r for r in output.values() if r['loss_bounds_bb'] is not None]
    n=sum(r['stochastic_action_intervals'] for r in output.values())
    # Union bound across the marginal 95% intervals (no independence needed).
    # Across multiple hypotheses this is conditional on all declared models.
    span=[min(r['loss_bounds_bb'][0] for r in covered),max(r['loss_bounds_bb'][1] for r in covered)] if len(covered)==len(output) else None
    point_span=[min(r['conditional_ev_loss_bb'] for r in covered),max(r['conditional_ev_loss_bb'] for r in covered)] if span is not None else None
    return {'variant':5,'status':'CONDITIONAL_MODEL_ONLY','baseline':'fold_zero_incremental',
            'chosen_action_declared':label(chosen),'scenarios':output,
            'coverage':{'hypotheses_submitted':len(output),'hypotheses_comparable':len(covered),
                        'no_match':sum(r['status']=='NO_MATCH' for r in output.values()),
                        'insufficient_data':sum(r['status']=='INSUFFICIENT_DATA' for r in output.values()),
                        'full_action_space_covered':False},
            'conditional_loss_point_span_bb':point_span,'conditional_loss_bounds_span_bb':span,
            'span_is_calibrated_confidence_interval':False,
            'sampling_interval_joint_coverage_lower_bound':max(0,1-.05*n),
            'stochastic_action_intervals':n,'range_or_response_uncertainty_included':False,
            'financial_result_bb':None,'variance_attribution':None,'ev_loss_bb':None,
            'action_observed_verified':False,'strategic_error_established':False,
            'gto_solution':False,'automatic_clip_selection_authorized':False}
