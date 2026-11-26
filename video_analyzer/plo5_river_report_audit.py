"""Recompute a restricted PLO5 river report from declared ranges and policies.
No CFR iterations, no GTO certification, and no claims about the video.
"""
import hashlib
import json
import math
from plo5_river_solver import prepare


def need(ok, message):
    if not ok:
        raise ValueError(message)


def close(value, expected):
    return type(value) in (int, float) and math.isfinite(value) and math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-9)


def prob(value):
    need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, 'Invalid policy probability')
    return value


def verify(game, report):
    """Audit each legal holding, probability, EV and global best-response gap."""
    need(type(report) is dict and type(report.get('variant')) is int and report['variant']==5 and report.get('status')=='RESTRICTED_RIVER_GAME_APPROXIMATION', 'Invalid restricted report')
    need(all(report.get(k) is False for k in ('range_assumptions_verified','gto_solution','production_strategy_authorized','video_verified','strategic_error_established')), 'Unsupported certainty')
    key=hashlib.sha256(json.dumps(game,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    need(report.get('game')==game and report.get('game_sha256')==key, 'River game identity mismatch')
    a,v,pairs,input_mass,mass,p,bb=prepare(game,report.get('iterations'))
    for k,expected in [('legal_joint_deals',len(pairs)),('input_joint_weight',input_mass),('legal_joint_weight',mass),('excluded_joint_weight',input_mass-mass)]:
        need(type(report.get(k)) is int and report[k]==expected, 'Joint deal count mismatch')
    am=[0.]*len(a);vm=[0.]*len(v)
    for i,j,w,_,_ in pairs:am[i]+=w;vm[j]+=w
    def index(rows,holdings,marginals):
        need(type(rows) is list and len(rows)==sum(m>0 for m in marginals),'Policy roster mismatch')
        out={}
        for r in rows:
            need(type(r) is dict and type(r.get('cards')) is list and all(type(c) is str for c in r['cards']), 'Invalid policy holding')
            h=tuple(r['cards']);need(h not in out,'Duplicate policy holding');out[h]=r
        need(set(out)=={h for (h,_),m in zip(holdings,marginals) if m>0},'Policy holding mismatch')
        for (h,_),m in zip(holdings,marginals):
            if m:need(close(out[h].get('joint_marginal'),m),'Marginal mismatch')
        return out
    hero=index(report.get('hero_strategy'),a,am);opp=index(report.get('opponent_strategy'),v,vm)
    x=[0.]*len(a);y=[0.]*len(v)
    for i,(h,_) in enumerate(a):
        if not am[i]:continue
        actions=hero[h].get('actions');need(type(actions) is list and len(actions)==2 and all(type(z) is dict for z in actions),'Invalid hero actions')
        c,b=actions;need(c.get('action')=='check' and b.get('action')=='bet' and type(b.get('extra_chips')) is int and b['extra_chips']==game['bet_chips'],'Action sizing mismatch')
        x[i]=prob(b.get('frequency'));need(close(prob(c.get('frequency')),1-x[i]),'Hero frequency sum mismatch')
    for j,(h,_) in enumerate(v):
        if not vm[j]:continue
        row=opp[h];y[j]=prob(row.get('call_frequency'));need(close(prob(row.get('fold_frequency')),1-y[j]),'Opponent frequency sum mismatch')
    # Recompute each weighted payoff from the declared policies, without solving again.
    check=[0.]*len(a);bet=[0.]*len(a);fold=[0.]*len(v);call=[0.]*len(v)
    for i,j,w,c,q in pairs:
        check[i]+=w*c;bet[i]+=w*((1-y[j])+y[j]*q)
        fold[j]+=w*x[i];call[j]+=w*x[i]*q
    scale=p/bb
    for i,(h,_) in enumerate(a):
        if am[i]:
            for row,val in zip(hero[h]['actions'],(check[i],bet[i])):need(close(row.get('ev_bb'),val/am[i]*scale),'Action EV mismatch')
    value=sum((1-x[i])*check[i]+x[i]*bet[i] for i in range(len(a)))
    upper=sum(map(max,zip(check,bet)))
    lower=sum((1-x[i])*check[i] for i in range(len(a)))+sum(map(min,zip(fold,call)))
    gap=max(0.,upper-lower)
    for k,expected in [('hero_value_bb',value*scale),('best_response_upper_bb',upper*scale),('best_response_lower_bb',lower*scale),('nash_gap_bb',gap*scale),('gap_fraction_of_pot',gap)]:
        need(close(report.get(k),expected),'Best-response certificate mismatch')
    need(report.get('within_one_percent_pot_gap') is (gap<=.01),'Gap flag mismatch')
    if 'solver_algorithm' in report:
        need(report['solver_algorithm']=='cfr_plus','Unknown accelerated solver')
        target=prob(report.get('target_gap_fraction_of_pot'))
        need(report.get('target_reached') is (gap<=target) and type(report.get('cache_hit')) is bool and (not report['cache_hit'] or report['target_reached']),'Invalid stopping metadata')
    return {'variant':5,'policy_math_consistent':True,'legal_joint_deals':len(pairs),'gap_fraction_of_pot':gap,'solver_reruns':0,'gto_solution':False,'video_verified':False}
