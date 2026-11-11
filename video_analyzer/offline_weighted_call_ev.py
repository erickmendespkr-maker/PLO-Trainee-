"""Offline weighted-range equity -> conditional call EV. No video/GTO claims.

Assumptions: heads-up, showdown after call, no rake, side pots or future
betting. Each range is independently supplied; CI only captures Monte Carlo
sampling uncertainty conditional on that range.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path
from offline_weighted_ranges import equity, exact_river

IDENT = re.compile(r'[A-Za-z0-9_.-]{1,80}\Z')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(x, minimum, maximum):
    return type(x) in (int, float) and math.isfinite(x) and minimum <= x <= maximum


def analyze(s):
    require(type(s) is dict and set(s) == {
        'schema_version','source_type','scenario_id','hero','board',
        'pot_before_call_bb','call_cost_bb','ranges','iterations','seed',
        'assumptions'}, 'invalid scenario fields')
    require(type(s['schema_version']) is int and s['schema_version'] == 1 and
            s['source_type'] == 'manually_authored_hypothetical_not_video_verified' and
            type(s['scenario_id']) is str and IDENT.fullmatch(s['scenario_id']),
            'hypothetical identity required')
    require(s['assumptions'] == {
        'heads_up':True,'showdown_after_call':True,'no_rake':True,
        'no_side_pots':True,'no_future_betting':True,
        'equity_includes_tie_fraction':True}, 'unsupported EV assumptions')
    p,c=s['pot_before_call_bb'],s['call_cost_bb']
    require(finite(p,0,1e6) and finite(c,1e-6,1e6),'invalid pot/call')
    require(type(s['iterations']) is int and 100 <= s['iterations'] <= 1000000 and
            type(s['seed']) is int and 0 <= s['seed'] <= 2**32-1,
            'invalid Monte Carlo parameters')
    require(type(s['ranges']) is list and 2 <= len(s['ranges']) <= 12,
            '2-12 hypothetical ranges required')
    seen=set()
    rows=[]
    for r in s['ranges']:
        require(type(r) is dict and set(r)=={'range_id','holdings'},
                'invalid range schema')
        rid=r['range_id']
        require(type(rid) is str and IDENT.fullmatch(rid) and rid not in seen,
                'duplicate or invalid range ID')
        seen.add(rid)
        # Exact weighted river has no sampling interval; a degenerate interval
        # represents mathematical exactness conditional on the supplied holdings.
        if len(s['board']) == 5:
            result=exact_river(s['hero'],s['board'],r['holdings'])
            q=result['equity']
            interval=[q,q]
            method='exact_weighted_river'
            trials=None
        else:
            result=equity(s['hero'],s['board'],r['holdings'],
                          iterations=s['iterations'],seed=s['seed'])
            q=result['equity']
            interval=result['ci95_conservative']
            method='weighted_range_monte_carlo'
            trials=result['trials']
        lo,hi=interval
        ev=lambda x: x*(p+c)-c
        ev_interval=[ev(lo),ev(hi)]
        label=('positive_under_interval' if ev_interval[0]>0 else
               'negative_under_interval' if ev_interval[1]<0 else
               'uncertain_or_break_even')
        rows.append({'range_id':rid,'equity':q,'equity_interval_conditional':interval,
                     'ev_call_bb':ev(q),'ev_interval_conditional_bb':ev_interval,
                     'conditional_label':label,'equity_method':method,
                     'trials':trials,'seed':s['seed'] if trials is not None else None,
                     'range_audit':result['range_audit'],
                     'range_is_user_assumption':True,
                     'range_uncertainty_included_in_interval':False})
    labels={r['conditional_label'] for r in rows}
    robust=labels in ({'positive_under_interval'},{'negative_under_interval'})
    return {'schema_version':1,'analysis_status':'hypothetical_weighted_range_ev_not_video_verified',
            'scenario_id':s['scenario_id'],'pot_before_call_bb':p,'call_cost_bb':c,
            'break_even_equity':c/(p+c),'range_results':rows,
            'range_sensitive':not robust,
            'source_hand_reconstruction_verified':False,
            'strategic_error_established':False,
            'automatic_clip_selection_authorized':False,'gto_solution':False,
            'range_uncertainty_included_in_interval':False,
            'warning':'Conditional heads-up showdown EV. Ranges are assumptions, not observed video facts; no GTO or real-hand verdict.'}


def unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,'duplicate JSON key')
        d[k]=v
    return d


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hypothetical_scenario_json')
    args=parser.parse_args()
    path=Path(args.hypothetical_scenario_json)
    require(path.is_file() and not path.is_symlink() and
            0<path.stat().st_size<=262144,'invalid scenario file')
    scenario=json.loads(path.read_text('utf-8'),object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    print(json.dumps(analyze(scenario),allow_nan=False,indent=2))


if __name__=='__main__':
    main()
