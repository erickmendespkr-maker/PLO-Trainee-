"""Conservative offline equity and call-EV uncertainty; never GTO."""
import math

def enrich(report, pot_before_call_bb, call_cost_bb, *, confidence=0.95):
    """Attach conservative Hoeffding bounds to an existing unverified report.

    Range/OCR uncertainty is NOT included. Pot includes the opponent wager.
    """
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise ValueError('invalid report schema')
    q=report.get('equity')
    n=report.get('trials_or_runouts')
    method=report.get('method')
    ev=report.get('conditional_call_ev')
    def number(v):
        return type(v) in (int,float) and math.isfinite(v)
    if not number(q) or not 0<=q<=1 or type(n) is not int or n<=0:
        raise ValueError('invalid equity or samples')
    if method not in ('MONTE_CARLO','EXACT'):
        raise ValueError('invalid method')
    if not number(confidence) or not 0<confidence<1:
        raise ValueError('invalid confidence')
    if not number(pot_before_call_bb) or not number(call_cost_bb) or call_cost_bb<=0 or pot_before_call_bb<call_cost_bb:
        raise ValueError('invalid pot or call')
    if report.get('decision_status')!='REVIEW_REQUIRED' or report.get('video_evidence_status')!='NOT_VERIFIED':
        raise ValueError('cannot promote evidence')
    if not isinstance(ev,dict) or ev.get('is_gto') is not False or not number(ev.get('call_ev_bb')):
        raise ValueError('invalid EV')
    expected=q*(pot_before_call_bb+call_cost_bb)-call_cost_bb
    if abs(ev['call_ev_bb']-expected)>1e-7:
        raise ValueError('inconsistent EV')
    if method=='EXACT':
        lo=hi=q
        label='EXACT_ENUMERATION'
    else:
        radius=math.sqrt(math.log(2/(1-confidence))/(2*n))
        lo=max(0.,q-radius)
        hi=min(1.,q+radius)
        label='HOEFFDING_IID_BOUNDED_POT_SHARE'
    out=dict(report)
    out['equity_ci95']=[lo,hi] if confidence==.95 else None
    out['equity_ci_status']=label
    out['conditional_call_ev']=dict(ev)
    out['conditional_call_ev']['ev_lower_bb']=lo*(pot_before_call_bb+call_cost_bb)-call_cost_bb
    out['conditional_call_ev']['ev_upper_bb']=hi*(pot_before_call_bb+call_cost_bb)-call_cost_bb
    out['uncertainty_audit']={'confidence':confidence,'method':label,'fixed_range_assumption':True,
        'iid_runout_assumption':method=='MONTE_CARLO','range_uncertainty_included':False,
        'ocr_uncertainty_included':False,'review_required':True,'is_gto':False}
    return out
