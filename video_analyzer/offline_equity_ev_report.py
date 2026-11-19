"""Offline PLO5/PLO6 conditional equity/EV report; not GTO."""
import math
from statistics import NormalDist
try:
    from video_analyzer.pokerinfra_bridge import request, run
    from video_analyzer.offline_ev_scenarios import call_ev
except ImportError:
    from pokerinfra_bridge import request, run
    from offline_ev_scenarios import call_ev

def wilson_interval(p,n):
    if type(n) is not int or n<=0 or type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1:
        raise ValueError('invalid sample')
    z=NormalDist().inv_cdf(.975)
    d=1+z*z/n
    c=(p+z*z/(2*n))/d
    r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,c-r),min(1,c+r)]

def analyze(variant,hero,opponents,board,pot_bb,call_bb,*,trials=10000,seed=1,evaluator=run):
    if not isinstance(opponents,list) or not opponents: raise ValueError('opponents required')
    payload=request('equity',variant,holes=[hero,*opponents],board=board,trials=trials,seed=seed)
    result=evaluator(payload)
    if not isinstance(result,dict) or type(result.get('runouts')) is not int or result['runouts']<=0 or not isinstance(result.get('players'),list) or len(result['players'])!=len(opponents)+1:
        raise ValueError('invalid evaluator result')
    hero_result=result['players'][0]
    if not isinstance(hero_result,dict): raise ValueError('invalid player result')
    for key in ('equity','win','tie'):
        v=hero_result.get(key)
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:
            raise ValueError('invalid probability')
    if hero_result['win']+hero_result['tie']>1+1e-9: raise ValueError('inconsistent probabilities')
    exact=result.get('exact') is True
    return {'schema_version':1,'variant':variant,'hero':payload['request']['players'][0],
        'opponents':payload['request']['players'][1:],'board':payload['request']['board'],
        'equity':hero_result['equity'],'win':hero_result['win'],'tie':hero_result['tie'],
        'win_probability_ci95':None if exact else wilson_interval(hero_result['win'],result['runouts']),
        'equity_ci95':None,
        'equity_ci_status':'EXACT_ENUMERATION' if exact else 'UNAVAILABLE_WITHOUT_RUNOUT_VARIANCE',
        'method':'EXACT' if exact else 'MONTE_CARLO','trials_or_runouts':result['runouts'],
        'seed':seed,'conditional_call_ev':call_ev(pot_bb,call_bb,hero_result['equity']),
        'range_model':'KNOWN_HANDS_OR_UNIFORM_RANDOM_OPPONENTS',
        'video_evidence_status':'NOT_VERIFIED','decision_status':'REVIEW_REQUIRED','is_gto':False}
