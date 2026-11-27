"""Offline PLO5 Bayesian range conditioning on explicit model frequencies.
Missing policy entries are not zero probability. No opponent inference
certificate or multiway independence claim.
"""
from fractions import Fraction
from math import isfinite
from plo5_pre_gto_context import cards,need

DECK={r+s for r in "23456789TJQKA" for s in "cdhs"}

def condition(rows,frequencies,dead=()):
    need(type(rows) is list and bool(rows),"Empty range")
    need(type(dead) in (list,tuple) and all(type(c) is str and c in DECK for c in dead) and len(set(dead))==len(dead),"Invalid blockers")
    need(type(frequencies) is dict,"Explicit likelihood map required")
    blocked=set(dead);seen=set();posterior=[];prior=Fraction(0);mass=Fraction(0);missing=0
    for row in rows:
        need(type(row) is dict and set(row)=={"cards","weight"},"Invalid range row")
        h=tuple(cards(row["cards"]));w=row["weight"]
        need(type(w) is int and w>0,"Invalid weight")
        need(h not in seen,"Duplicate holding");seen.add(h)
        if blocked.intersection(h):continue
        prior+=w
        if h not in frequencies:
            missing+=1;continue
        f=frequencies[h]
        need(type(f) in (int,float) and isfinite(f) and 0<=f<=1,"Invalid action likelihood")
        v=w*Fraction(str(f));mass+=v
        if v:posterior.append((h,v))
    base=dict(variant=5,missing_holdings=missing,gto_solution=False,range_assumptions_verified=False)
    if not prior:return dict(base,status="NO_LEGAL_RANGE",rows=[])
    if missing:return dict(base,status="INCOMPLETE_POLICY",rows=[])
    if not mass:return dict(base,status="ZERO_ACTION_LIKELIHOOD",rows=[])
    return dict(base,status="CONDITIONAL_RANGE",action_probability=float(mass/prior),rows=[dict(cards=list(h),probability=float(v/mass),exact_probability=[(v/mass).numerator,(v/mass).denominator]) for h,v in sorted(posterior)])

def selftest():
    a=["As","Ks","Qs","Js","Ts"];b=["Ah","Kh","Qh","Jh","Th"]
    rows=[dict(cards=a,weight=3),dict(cards=b,weight=1)]
    f={tuple(cards(a)):.25,tuple(cards(b)):.75}
    r=condition(rows,f)
    assert r["action_probability"]==.375
    assert [x["probability"] for x in r["rows"]]==[.5,.5]
    assert condition(rows,{},[])["status"]=="INCOMPLETE_POLICY"
    assert condition(rows,f,["As"])["rows"][0]["probability"]==1
    assert condition(rows,{k:0 for k in f})["status"]=="ZERO_ACTION_LIKELIHOOD"
    assert condition(rows,f,["As","Ah"])["status"]=="NO_LEGAL_RANGE"
if __name__=="__main__":selftest()
