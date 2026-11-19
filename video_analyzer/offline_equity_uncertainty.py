"""Conservative uncertainty bounds for offline Monte Carlo Omaha equity."""
import math
try:
    from video_analyzer.offline_ev_scenarios import call_ev
except ImportError:
    from offline_ev_scenarios import call_ev

def equity_bound(equity, trials, confidence=0.95):
    if type(equity) not in (int,float) or not math.isfinite(equity) or not 0<=equity<=1:
        raise ValueError("invalid equity")
    if type(trials) is not int or trials<=0:
        raise ValueError("invalid trials")
    if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<confidence<1:
        raise ValueError("invalid confidence")
    radius=math.sqrt(math.log(2/(1-confidence))/(2*trials))
    return {"lower":max(0.,equity-radius),"upper":min(1.,equity+radius),
        "method":"HOEFFDING_IID_BOUNDED_POT_SHARE","confidence":confidence,
        "trials":trials,"assumptions":["iid_runouts","pot_share_between_zero_and_one","fixed_range_model"]}

def conditional_call_ev_bound(pot_before_call_bb,call_cost_bb,equity,trials,confidence=0.95):
    bounds=equity_bound(equity,trials,confidence)
    low=call_ev(pot_before_call_bb,call_cost_bb,bounds["lower"])
    high=call_ev(pot_before_call_bb,call_cost_bb,bounds["upper"])
    mid=call_ev(pot_before_call_bb,call_cost_bb,equity)
    return {"equity":bounds,"call_ev_bb":mid["call_ev_bb"],
        "call_ev_lower_bb":low["call_ev_bb"],"call_ev_upper_bb":high["call_ev_bb"],
        "range_uncertainty_included":False,"video_uncertainty_included":False,
        "is_gto":False,"review_required":True}
