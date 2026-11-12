"""Bind offline human review to hypothetical weighted-range EV; no strategic verdict."""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9_.-]{1,80}\Z')

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def finite(x, lo, hi):
    return type(x) in (int, float) and math.isfinite(x) and lo <= x <= hi

def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()

def bind(review, gate, ev, *, pot_tolerance_bb=0.01):
    """Bind three independent artifacts; all output remains conditional, never GTO."""
    require(type(review) is dict and type(gate) is dict and type(ev) is dict, 'all three objects required')
    require(type(review.get('schema_version')) is int and review['schema_version'] == 1, 'review schema mismatch')
    require(type(gate.get('schema_version')) is int and gate['schema_version'] == 1 and type(ev.get('schema_version')) is int and ev['schema_version'] == 1, 'result schema mismatch')
    hand = review.get('hand_id')
    require(type(hand) is str and IDENT.fullmatch(hand) and gate.get('hand_id') == hand, 'hand ID mismatch')
    sha = review.get('source_video_sha256')
    require(type(sha) is str and HEX.fullmatch(sha) and gate.get('source_video_sha256') == sha, 'video hash mismatch')
    table = review.get('table_id')
    require(type(table) is int and 1 <= table <= 4 and type(gate.get('table_id')) is int and gate['table_id'] == table, 'table mismatch')
    start, end = review.get('start_seconds'), review.get('end_seconds')
    require(finite(start, 0, 5400) and finite(end, 0, 5400) and 0.1 <= end-start <= 180, 'invalid time interval')
    require(finite(pot_tolerance_bb, 0, 0.1), 'invalid pot tolerance')
    require(gate.get('analysis_status') in ('INSUFFICIENT_DATA', 'READY_FOR_CONDITIONAL_MODEL') and gate.get('source_hand_reconstruction_verified') is False and gate.get('strategic_error_established') is False and gate.get('gto_solution') is False, 'unsafe review gate flags')
    missing = gate.get('missing_or_unconfirmed')
    require(type(missing) is list and all(type(x) is str and IDENT.fullmatch(x) for x in missing) and missing == sorted(set(missing)), 'invalid missing evidence')
    ready = gate['analysis_status'] == 'READY_FOR_CONDITIONAL_MODEL'
    require(ready == (len(missing) == 0), 'inconsistent review readiness')
    require(ev.get('analysis_status') == 'hypothetical_weighted_range_ev_not_video_verified' and ev.get('source_hand_reconstruction_verified') is False and ev.get('strategic_error_established') is False and ev.get('automatic_clip_selection_authorized') is False and ev.get('gto_solution') is False and ev.get('range_uncertainty_included_in_interval') is False, 'unsafe EV provenance')
    scenario = ev.get('scenario_id')
    require(type(scenario) is str and IDENT.fullmatch(scenario), 'invalid scenario')
    p, c = review.get('pot_bb'), review.get('call_bb')
    ep, ec = ev.get('pot_before_call_bb'), ev.get('call_cost_bb')
    require(all(finite(v, 0, 1e6) for v in (p, c, ep, ec)) and abs(p-ep) <= pot_tolerance_bb and abs(c-ec) <= pot_tolerance_bb and c > 0 and review.get('action') == 'call', 'EV does not match reviewed call and pot')
    require(finite(ev.get('break_even_equity'), 0, 1) and abs(ev['break_even_equity'] - ec/(ep+ec)) <= 1e-8, 'invalid pot odds')
    rows = ev.get('range_results')
    require(type(rows) is list and 2 <= len(rows) <= 12, 'invalid range results')
    labels, ids = set(), set()
    for r in rows:
        require(type(r) is dict, 'invalid EV row')
        rid = r.get('range_id')
        require(type(rid) is str and IDENT.fullmatch(rid) and rid not in ids, 'invalid or repeated range')
        ids.add(rid)
        q, ci, value, bounds = (r.get(k) for k in ('equity', 'equity_interval_conditional', 'ev_call_bb', 'ev_interval_conditional_bb'))
        require(finite(q, 0, 1) and type(ci) is list and len(ci) == 2 and all(finite(x, 0, 1) for x in ci) and ci[0] <= q <= ci[1], 'invalid equity interval')
        require(finite(value, -1e6, 1e6) and type(bounds) is list and len(bounds) == 2 and all(finite(x, -1e6, 1e6) for x in bounds) and abs(value-(q*(ep+ec)-ec)) < 1e-5 and all(abs(v-(x*(ep+ec)-ec)) < 1e-5 for v,x in zip(bounds,ci)), 'EV/equity disagreement')
        label = ('positive_under_interval' if bounds[0] > 0 else 'negative_under_interval' if bounds[1] < 0 else 'uncertain_or_break_even')
        require(r.get('conditional_label') == label and r.get('range_is_user_assumption') is True and r.get('range_uncertainty_included_in_interval') is False, 'unsafe or inconsistent range row')
        labels.add(label)
    sensitive = labels not in ({'positive_under_interval'}, {'negative_under_interval'})
    require(ev.get('range_sensitive') is sensitive, 'range sensitivity mismatch')
    return {'schema_version': 1, 'analysis_status': 'CONDITIONAL_MODEL_REVIEW_ONLY' if ready else 'INSUFFICIENT_DATA', 'hand_id': hand, 'table_id': table, 'source_video_sha256': sha, 'start_seconds': start, 'end_seconds': end, 'review_record_sha256': digest(review), 'review_gate_sha256': digest(gate), 'hypothetical_ev_sha256': digest(ev), 'hypothetical_scenario_id': scenario, 'missing_or_unconfirmed': missing, 'range_sensitive': sensitive, 'range_count': len(rows), 'source_hand_reconstruction_verified': False, 'strategic_error_established': False, 'gto_solution': False, 'automatic_clip_selection_authorized': False, 'range_uncertainty_included_in_interval': False, 'warning': 'Ranges are unobserved hypotheses; evidence readiness does not prove opponent ranges or a strategic mistake. No automatic clip selection or GTO claim is authorized.'}

def strict_read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 262144, 'unsafe JSON file')
    def unique(pairs):
        d = {}
        for k,v in pairs:
            require(k not in d, 'duplicate JSON key')
            d[k] = v
        return d
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review_json'); parser.add_argument('gate_json'); parser.add_argument('weighted_ev_json')
    a = parser.parse_args()
    print(json.dumps(bind(strict_read(a.review_json), strict_read(a.gate_json), strict_read(a.weighted_ev_json)), indent=2, allow_nan=False))

if __name__ == '__main__':
    main()
