"""Opt-in accelerated restricted river model, preserving the existing report contract."""
import hashlib
import json
import math

from plo5_cfr_restricted import optimize, utilities, certificate
from plo5_restricted_cache import resolve


def render(game, prepared, result):
    """Translate a policy into the original solver's conditional report format."""
    a,v,pairs,input_mass,mass,p,bb=prepared
    x,y=result['hero_bet_probabilities'],result['opponent_call_probabilities']
    if (len(x)!=len(a) or len(y)!=len(v) or
            any(type(z) not in (int,float) or not math.isfinite(z) or not 0<=z<=1 for z in x+y)):
        raise ValueError('Invalid solver policy')
    cert=certificate(pairs,x,y,len(a),len(v))
    ac,_=utilities(pairs,x,y,len(a),len(v));am=[0.]*len(a);vm=[0.]*len(v)
    for i,j,w,_,_ in pairs:am[i]+=w;vm[j]+=w
    scale=p/bb
    rows=[{'cards':list(h),'joint_marginal':am[i],'actions':[
        {'action':'check','frequency':1-x[i],'ev_bb':ac[i][0]/am[i]*scale},
        {'action':'bet','extra_chips':game['bet_chips'],'frequency':x[i],'ev_bb':ac[i][1]/am[i]*scale}]}
        for i,(h,_) in enumerate(a) if am[i]]
    opponents=[{'cards':list(h),'joint_marginal':vm[j],'fold_frequency':1-y[j],'call_frequency':y[j]}
               for j,(h,_) in enumerate(v) if vm[j]]
    digest=hashlib.sha256(json.dumps(game,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return {'variant':5,'status':'RESTRICTED_RIVER_GAME_APPROXIMATION','game_sha256':digest,'game':game,
            'iterations':result['iterations'],'legal_joint_deals':len(pairs),'input_joint_weight':input_mass,
            'legal_joint_weight':mass,'excluded_joint_weight':input_mass-mass,'hero_value_bb':cert['value']*scale,
            'best_response_upper_bb':cert['upper']*scale,'best_response_lower_bb':cert['lower']*scale,
            'nash_gap_bb':cert['gap']*scale,'gap_fraction_of_pot':cert['gap'],'within_one_percent_pot_gap':cert['gap']<=.01,
            'hero_strategy':rows,'opponent_strategy':opponents,
            'scope':'HU river, check forces showdown, one fixed bet, fold/call only, zero rake, explicit ranges, initial pot sunk',
            'solver_algorithm':result['algorithm'],'target_gap_fraction_of_pot':result['target_gap_fraction_of_pot'],
            'target_reached':cert['gap']<=result['target_gap_fraction_of_pot'],'cache_hit':result.get('cache_hit',False),
            'range_assumptions_verified':False,'gto_solution':False,'production_strategy_authorized':False,
            'video_verified':False,'strategic_error_established':False}


def solve(game, iterations=10000, *, cache=None, target=.01, check_every=50):
    from plo5_river_solver import prepare
    prepared=prepare(game,iterations)
    a,v,pairs,*_=prepared
    options={'iterations':iterations,'target':target,'check_every':check_every,'algorithm':'cfr_plus'}
    result=optimize(pairs,len(a),len(v),**options) if cache is None else resolve(cache,pairs,len(a),len(v),**options)
    return render(game,prepared,result)
