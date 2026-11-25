"""Offline conditional PLO5 river game: check/showdown or one bet, fold/call.

Original tabular regret matching, exact weighted legal deal enumeration.
Not a full betting tree, inferred range, six-max solution or production GTO.
"""
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from plo5_evaluator import evaluate
from offline_omaha_showdown import _cards


def need(ok, message):
    if not ok:
        raise ValueError(message)


def integer(v, lo, hi):
    need(type(v) is int and lo <= v <= hi, 'Invalid integer parameter')
    return v


def range_rows(entries, board):
    need(type(entries) is list and 1 <= len(entries) <= 128, 'Expected 1–128 explicit holdings')
    seen=set(); legal=[]; total=0
    for e in entries:
        need(type(e) is dict and set(e)=={'cards','weight'}, 'Invalid holding')
        cards=tuple(sorted(_cards(e['cards'],5))); w=integer(e['weight'],1,10**9)
        need(cards not in seen,'Duplicate holding');seen.add(cards);total+=w
        if not set(cards)&set(board):legal.append((cards,w))
    need(legal,'All holdings blocked by board')
    return sorted(legal),total


def prepare(game, iterations):
    need(type(game) is dict and set(game)=={'variant','board','pot_chips','bet_chips','hero_stack_chips','opponent_stack_chips','bb_chips','hero_range','opponent_range'},'Invalid game')
    need(type(game['variant']) is int and game['variant']==5,'PLO5 only')
    board=_cards(game['board'],5);p=integer(game['pot_chips'],1,10**9);b=integer(game['bet_chips'],1,p)
    for k in ('hero_stack_chips','opponent_stack_chips'):need(integer(game[k],1,10**9)>=b,'Bet exceeds remaining stack')
    bb=integer(game['bb_chips'],1,10**9);integer(iterations,1,50000)
    a,wa=range_rows(game['hero_range'],board);v,wv=range_rows(game['opponent_range'],board)
    need(len(a)*len(v)<=4096,'Joint pairing budget exceeded')
    ar=[evaluate(h,board)['rank'] for h,w in a];vr=[evaluate(h,board)['rank'] for h,w in v]
    raw=[];mass=0
    for i,(h,w) in enumerate(a):
        for j,(o,z) in enumerate(v):
            if set(h)&set(o):continue
            q=1.0 if ar[i]>vr[j] else .5 if ar[i]==vr[j] else 0.0
            weight=w*z;mass+=weight;raw.append((i,j,weight,q))
    need(mass and iterations*len(raw)<=4000000,'No disjoint deals or iteration budget exceeded')
    # Scale payoffs by P for numerical stability; constant-sum total P.
    pairs=[(i,j,w/mass,q,q*(1+2*b/p)-b/p) for i,j,w,q in raw]
    return a,v,pairs,wa*wv,mass,p,bb


def probability(r):
    x,y=max(0.,r[0]),max(0.,r[1]);return y/(x+y) if x+y else .5


def utilities(pairs, x, y, na, nv):
    # x: bet probability, y: call probability. Hero utilities for both actions,
    # villain's minimization utility for fold/call at its decision infoset.
    ac=[[0.,0.] for _ in range(na)];vc=[[0.,0.] for _ in range(nv)]
    for i,j,w,check,call in pairs:
        ac[i][0]+=w*check;ac[i][1]+=w*(1-y[j]+y[j]*call)
        vc[j][0]+=w*x[i];vc[j][1]+=w*x[i]*call
    return ac,vc


def solve(game, iterations=10000):
    a,v,pairs,input_mass,mass,p,bb=prepare(game,iterations);na,nv=len(a),len(v)
    ra=[[0.,0.] for _ in a];rv=[[0.,0.] for _ in v];sa=[0.]*na;sv=[0.]*nv
    for _ in range(iterations):
        x=list(map(probability,ra));y=list(map(probability,rv))
        ac,vc=utilities(pairs,x,y,na,nv)
        for i,(c,b) in enumerate(ac):
            u=(1-x[i])*c+x[i]*b;ra[i][0]+=c-u;ra[i][1]+=b-u;sa[i]+=x[i]
        for j,(f,c) in enumerate(vc):
            u=(1-y[j])*f+y[j]*c;rv[j][0]+=u-f;rv[j][1]+=u-c;sv[j]+=y[j]
    x=[z/iterations for z in sa];y=[z/iterations for z in sv]
    ac,vc=utilities(pairs,x,y,na,nv)
    am=[0.]*na;vm=[0.]*nv
    for i,j,w,_,_ in pairs:am[i]+=w;vm[j]+=w
    value=sum((1-x[i])*c+x[i]*b for i,(c,b) in enumerate(ac))
    upper=sum(max(c,b) for c,b in ac)
    lower=sum((1-x[i])*c for i,(c,b) in enumerate(ac))+sum(min(f,c) for f,c in vc)
    gap=max(0.,upper-lower);scale=p/bb
    need(all(math.isfinite(z) for z in (value,upper,lower,gap)) and lower<=value+1e-10<=upper+2e-10,'Invalid numerical best-response bounds')
    rows=[]
    for i,(h,w) in enumerate(a):
        if not am[i]:continue
        rows.append({'cards':list(h),'joint_marginal':am[i],'actions':[{'action':'check','frequency':1-x[i],'ev_bb':ac[i][0]/am[i]*scale},{'action':'bet','extra_chips':game['bet_chips'],'frequency':x[i],'ev_bb':ac[i][1]/am[i]*scale}]})
    opponents=[{'cards':list(h),'joint_marginal':vm[j],'fold_frequency':1-y[j],'call_frequency':y[j]} for j,(h,w) in enumerate(v) if vm[j]]
    canonical=json.dumps(game,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'variant':5,'status':'RESTRICTED_RIVER_GAME_APPROXIMATION','game_sha256':hashlib.sha256(canonical).hexdigest(),'game':game,'iterations':iterations,'legal_joint_deals':len(pairs),'input_joint_weight':input_mass,'legal_joint_weight':mass,'excluded_joint_weight':input_mass-mass,'hero_value_bb':value*scale,'best_response_upper_bb':upper*scale,'best_response_lower_bb':lower*scale,'nash_gap_bb':gap*scale,'gap_fraction_of_pot':gap,'within_one_percent_pot_gap':gap<=.01,'hero_strategy':rows,'opponent_strategy':opponents,'scope':'HU river, check forces showdown, one fixed bet, fold/call only, zero rake, explicit ranges, initial pot sunk','range_assumptions_verified':False,'gto_solution':False,'production_strategy_authorized':False,'video_verified':False,'strategic_error_established':False}


def main(argv=None):
    import argparse
    from plo5_session_export import load, write
    from offline_video_ingest_probe import sha256
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('game');p.add_argument('output');p.add_argument('--iterations',type=int,default=10000);a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    game,h=load(a.game);result=solve(game,a.iterations);need(sha256(a.game)==h,'Input changed');result['input_sha256']=h;write(out,result);return 0


if __name__=='__main__':raise SystemExit(main())
