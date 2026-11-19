"""Offline conditional heads-up EV and range sensitivity. Not a GTO solver."""
import math

def finite(x, name, minimum=0, maximum=None):
    if type(x) not in (int,float) or not math.isfinite(x) or x < minimum or (maximum is not None and x > maximum):
        raise ValueError("invalid "+name)
    return float(x)

def call_ev(pot_before_call_bb, call_cost_bb, equity, rake_fraction=0):
    p=finite(pot_before_call_bb,"pot")
    c=finite(call_cost_bb,"call")
    q=finite(equity,"equity",0,1)
    r=finite(rake_fraction,"rake",0,1)
    if c == 0 or p < c: raise ValueError("call must be positive and included in opponent wager/pot")
    final=p+c
    return {"call_ev_bb":q*final*(1-r)-c,
            "required_equity":c/(final*(1-r)) if r<1 else None,
            "fold_ev_bb":0.0,
            "assumptions":["heads_up","full_equity_realization","no_future_bets","no_side_pots","flat_uncapped_rake"],
            "is_gto":False}

def range_sensitivity(pot_before_call_bb,call_cost_bb,scenarios,rake_fraction=0):
    if not isinstance(scenarios,list) or not scenarios: raise ValueError("missing scenarios")
    names=set()
    results=[]
    for s in scenarios:
        if not isinstance(s,dict) or set(s)!={"range_label","equity"}: raise ValueError("invalid scenario")
        name=s["range_label"]
        if not isinstance(name,str) or not name.strip() or len(name)>120 or name in names:
            raise ValueError("invalid or duplicate label")
        names.add(name)
        ev=call_ev(pot_before_call_bb,call_cost_bb,s["equity"],rake_fraction)
        results.append({"range_label":name,"equity":s["equity"],"call_ev_bb":ev["call_ev_bb"]})
    values=[r["call_ev_bb"] for r in results]
    conclusion=("POSITIVE_IN_ALL_SUPPLIED_SCENARIOS" if min(values)>0 else
                "NEGATIVE_IN_ALL_SUPPLIED_SCENARIOS" if max(values)<0 else
                "SENSITIVE_TO_RANGE_ASSUMPTIONS")
    return {"scenarios":results,"ev_min_bb":min(values),"ev_max_bb":max(values),
            "conclusion":conclusion,"review_required":True,
            "equities_are_assumptions_not_observations":True,"is_gto":False}
