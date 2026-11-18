"""Build a conservative offline review queue from audited showdown samples.

Input is *hypothetical* fixed-range simulation evidence, not a claim about a
recorded hand. A separate human review must establish the hand and timestamps.
No clip export or GTO inference is authorized by this module.
"""
from math import isfinite
from offline_decision_priority import prioritize_decisions
from offline_showdown_sample_audit import audit_showdown_samples


def build_review_queue(records, *, min_confidence=0.8, max_clips=20):
    """Compare observed CALL to FOLD (EV=0) under declared fixed-range samples.

    Each record: hand_id, decision_id, review_status, evidence_confidence,
    observed_action='call', and scenarios with range_label, pot_before_call,
    call_cost, hero_shares, seed and optional rake. Every range gets its own
    sampling interval; disagreement across ranges is never pooled away.
    """
    if not isinstance(records, list):
        raise ValueError('records must be a list')
    decisions = []
    audits = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('record must be an object')
        if record.get('observed_action') != 'call':
            raise ValueError('only observed call versus fold is supported')
        scenarios = record.get('scenarios')
        if not isinstance(scenarios, list):
            raise ValueError('scenarios must be a list')
        converted = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise ValueError('scenario must be an object')
            if scenario.get('seed') is None or not isinstance(scenario.get('range_label'), str):
                raise ValueError('scenario requires a seed and declared range label')
            audit = audit_showdown_samples(
                scenario.get('pot_before_call'), scenario.get('call_cost'),
                scenario.get('hero_shares'), rake=scenario.get('rake', 0.0),
                range_label=scenario['range_label'], seed=scenario['seed'])
            converted.append({'range_label': scenario['range_label'],
                              'ev_difference_interval': audit['call_ev_95pct_hoeffding_interval']})
            audits.append({'hand_id': record.get('hand_id'),
                           'decision_id': record.get('decision_id'), **audit})
        decisions.append({k: record.get(k) for k in
                          ('hand_id', 'decision_id', 'review_status', 'evidence_confidence')}
                         | {'scenarios': converted})
    queue = prioritize_decisions(decisions, min_confidence=min_confidence,
                                 max_clips=max_clips)
    queue['scenario_audits'] = audits
    queue['comparison'] = 'observed_call_minus_fold_showdown_only'
    queue['assumptions'] = ['no_future_betting', 'fixed_rake', 'iid_sampling_per_declared_range']
    queue['confidence_scope'] = 'sampling_only_conditional_on_each_declared_range'
    queue['range_uncertainty_quantified'] = False
    queue['clip_export_authorized'] = False
    return queue
