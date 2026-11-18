"""Conservative offline clip prioritization from independently audited EV scenarios.

No claim that any scenario is true of the recorded hand. No GTO labels.
"""
from math import isfinite


def prioritize_decisions(decisions, *, min_confidence=0.8, max_clips=20):
    """Return deterministic candidates; ambiguous or unreviewed hands never qualify.

    Each scenario supplies a [lower, upper] interval for incremental EV of the
    *observed* action versus a specified alternative, in chips. Intervals must
    include Monte Carlo sampling uncertainty; range scenarios are kept separate.
    A strictly negative upper bound across all scenarios indicates modeled loss.
    """
    if not isinstance(decisions, list):
        raise ValueError('decisions must be a list')
    if isinstance(max_clips, bool) or not isinstance(max_clips, int) or max_clips < 0:
        raise ValueError('invalid max_clips')
    if isinstance(min_confidence, bool) or not isinstance(min_confidence, (int, float)) or not isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError('invalid min_confidence')
    results = []
    seen = set()
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError('decision must be an object')
        key = (item.get('hand_id'), item.get('decision_id'))
        if any(not isinstance(x, str) or not x.strip() for x in key) or key in seen:
            raise ValueError('missing or duplicate decision identity')
        seen.add(key)
        confidence = item.get('evidence_confidence')
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('invalid evidence_confidence')
        scenarios = item.get('scenarios')
        if not isinstance(scenarios, list) or not scenarios:
            results.append({'hand_id': key[0], 'decision_id': key[1], 'status': 'INSUFFICIENT_DATA', 'reason': 'missing_scenarios'})
            continue
        bounds = []
        labels = set()
        for s in scenarios:
            if not isinstance(s, dict) or not isinstance(s.get('range_label'), str) or not s['range_label'].strip() or s['range_label'] in labels:
                raise ValueError('invalid or duplicate range label')
            labels.add(s['range_label'])
            interval = s.get('ev_difference_interval')
            if not isinstance(interval, (list, tuple)) or len(interval) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in interval) or interval[0] > interval[1]:
                raise ValueError('invalid EV interval')
            bounds.append((float(interval[0]), float(interval[1])))
        status = 'INSUFFICIENT_DATA'
        reason = 'review_or_confidence_missing'
        if item.get('review_status') == 'CONDITIONAL_ANALYSIS_PERMITTED' and confidence >= min_confidence:
            if all(hi < 0 for _, hi in bounds):
                status, reason = 'MODELLED_LOSS_CANDIDATE', 'negative_in_all_declared_ranges'
            elif all(lo > 0 for lo, _ in bounds):
                status, reason = 'MODELLED_GAIN_CANDIDATE', 'positive_in_all_declared_ranges'
            else:
                status, reason = 'RANGE_OR_SAMPLING_SENSITIVE', 'intervals_overlap_zero_or_disagree'
        row = {'hand_id': key[0], 'decision_id': key[1], 'status': status, 'reason': reason,
               'range_scenarios': len(bounds), 'evidence_confidence': float(confidence),
               'gto_claim_permitted': False, 'automatic_blunder_label_permitted': False}
        if status == 'MODELLED_LOSS_CANDIDATE':
            row['conservative_loss_lower_bound'] = min(-hi for _, hi in bounds)
        results.append(row)
    selected = sorted((r for r in results if r['status'] == 'MODELLED_LOSS_CANDIDATE'),
                      key=lambda r: (-r['conservative_loss_lower_bound'], r['hand_id'], r['decision_id']))[:max_clips]
    return {'candidates': results, 'selected_for_review': selected,
            'status': 'HYPOTHETICAL_REVIEW_QUEUE', 'clip_export_authorized': False,
            'notes': 'Human verification of hand and timestamps required before exporting annotated clips.'}
