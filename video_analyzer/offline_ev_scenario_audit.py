"""Audit conditional EV scenarios; does not infer ranges or claim GTO/real-hand errors."""
from __future__ import annotations
import math


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def audit(report):
    if type(report) is not dict or report.get('analysis_status') != 'hypothetical_weighted_range_ev_not_video_verified':
        raise ValueError('Only hypothetical weighted-range reports supported')
    for flag in ('source_hand_reconstruction_verified', 'strategic_error_established',
                 'automatic_clip_selection_authorized', 'gto_solution',
                 'range_uncertainty_included_in_interval'):
        if report.get(flag) is not False:
            raise ValueError('Unsupported verification claim: ' + flag)
    p, c, q0 = (report.get(k) for k in ('pot_before_call_bb', 'call_cost_bb', 'break_even_equity'))
    if not finite(p) or not finite(c) or p < 0 or c <= 0 or not finite(q0) or abs(q0 - c/(p+c)) > 1e-9:
        raise ValueError('Invalid pot odds')
    rows = report.get('range_results')
    if type(rows) is not list or not 2 <= len(rows) <= 12:
        raise ValueError('Need 2–12 range scenarios')
    seen, checked = set(), []
    for row in rows:
        if type(row) is not dict or type(row.get('range_id')) is not str or not row['range_id'] or row['range_id'] in seen:
            raise ValueError('Invalid or duplicate range ID')
        seen.add(row['range_id'])
        eq, interval, ev, ev_interval = (row.get(k) for k in
            ('equity', 'equity_interval_conditional', 'ev_call_bb', 'ev_interval_conditional_bb'))
        if not finite(eq) or not 0 <= eq <= 1 or type(interval) is not list or len(interval) != 2 or not all(finite(v) for v in interval) or not 0 <= interval[0] <= eq <= interval[1] <= 1:
            raise ValueError('Invalid equity interval')
        if not finite(ev) or type(ev_interval) is not list or len(ev_interval) != 2 or not all(finite(v) for v in ev_interval):
            raise ValueError('Invalid EV interval')
        expected = [(p+c)*v-c for v in interval]
        if abs(ev - ((p+c)*eq-c)) > 1e-7 or any(abs(x-y) > 1e-7 for x,y in zip(ev_interval,expected)):
            raise ValueError('EV not consistent with equity and pot odds')
        label = ('positive_under_interval' if expected[0] > 0 else
                 'negative_under_interval' if expected[1] < 0 else 'uncertain_or_break_even')
        if row.get('conditional_label') != label or row.get('range_is_user_assumption') is not True or row.get('range_uncertainty_included_in_interval') is not False:
            raise ValueError('Incorrect range provenance or conditional label')
        checked.append({'range_id':row['range_id'], 'ev_call_bb':ev,
                        'conditional_interval_bb':expected, 'conditional_label':label})
    signs = {x['conditional_label'] for x in checked}
    robust = signs in ({'positive_under_interval'}, {'negative_under_interval'})
    if report.get('range_sensitive') is not (not robust):
        raise ValueError('Range sensitivity flag inconsistent with scenario labels')
    lows = [x['conditional_interval_bb'][0] for x in checked]
    highs = [x['conditional_interval_bb'][1] for x in checked]
    return {'schema_version':1, 'analysis_status':'hypothetical_ev_scenario_audit_only',
            'scenario_id':report.get('scenario_id'), 'range_count':len(checked),
            'ev_call_scenario_envelope_bb':[min(lows),max(highs)],
            'all_scenarios_favor_call':signs == {'positive_under_interval'},
            'all_scenarios_favor_fold':signs == {'negative_under_interval'},
            'range_sensitive':not robust, 'source_hand_reconstruction_verified':False,
            'strategic_error_established':False, 'gto_solution':False,
            'range_uncertainty_quantified':False,
            'warning':'Scenario envelope is not a confidence interval across unknown opponent ranges; no real-hand verdict.',
            'scenarios':checked}
