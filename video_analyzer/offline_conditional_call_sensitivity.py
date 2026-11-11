"""Offline hypothetical heads-up call EV sensitivity. NOT a GTO solver or video verifier."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def number(x, lo, hi):
    return type(x) in (int, float) and math.isfinite(x) and lo <= x <= hi

def unique(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, 'duplicate JSON key')
        out[k] = v
    return out

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

ASSUMPTIONS = {'heads_up': True, 'showdown_after_call': True, 'no_rake': True,
               'no_side_pots': True, 'no_future_betting': True,
               'equity_includes_tie_fraction': True}
FIELDS = {'schema_version', 'source_type', 'scenario_id', 'pot_before_call_bb',
          'call_cost_bb', 'assumptions', 'ranges'}

def compute(s):
    require(type(s) is dict and set(s) == FIELDS, 'invalid scenario fields')
    require(type(s['schema_version']) is int and s['schema_version'] == 1 and
            s['source_type'] == 'manually_authored_hypothetical_not_video_verified' and
            type(s['scenario_id']) is str and 1 <= len(s['scenario_id']) <= 80 and
            all(c.isascii() and (c.isalnum() or c in '._-') for c in s['scenario_id']),
            'invalid scenario identity')
    p, c = s['pot_before_call_bb'], s['call_cost_bb']
    require(number(p, 0, 1e6) and number(c, .000001, 1e6), 'invalid pot/call')
    require(s['assumptions'] == ASSUMPTIONS, 'unsupported model assumptions')
    require(type(s['ranges']) is list and 2 <= len(s['ranges']) <= 12,
            'require 2-12 ranges')
    names, rows = set(), []
    for r in s['ranges']:
        require(type(r) is dict and set(r) == {
            'range_id', 'equity', 'equity_ci95', 'equity_method', 'iterations', 'seed'},
            'invalid range fields')
        name = r['range_id']
        require(type(name) is str and 1 <= len(name) <= 80 and
                all(x.isascii() and (x.isalnum() or x in '._-') for x in name) and
                name not in names, 'invalid or duplicate range')
        names.add(name)
        interval = r['equity_ci95']
        require(type(interval) is list and len(interval) == 2, 'invalid CI')
        lo, hi = interval
        q = r['equity']
        require(number(q, 0, 1) and number(lo, 0, 1) and number(hi, 0, 1) and
                lo <= q <= hi and
                r['equity_method'] == 'external_independent_monte_carlo_hypothesis' and
                type(r['iterations']) is int and 100 <= r['iterations'] <= 100000000 and
                type(r['seed']) is int and 0 <= r['seed'] <= 2**32 - 1,
                'invalid equity/Monte Carlo metadata')
        ev = lambda equity: equity * (p + c) - c
        low, center, high = (ev(x) for x in (lo, q, hi))
        label = ('positive_under_interval' if low > 0 else
                 'negative_under_interval' if high < 0 else 'uncertain_or_break_even')
        rows.append({'range_id': name, 'equity': q, 'equity_ci95': interval,
                     'ev_call_bb': round(center, 8),
                     'ev_call_ci95_bb': [round(low, 8), round(high, 8)],
                     'conditional_label': label,
                     'iterations': r['iterations'], 'seed': r['seed']})
    labels = {r['conditional_label'] for r in rows}
    robust = labels == {'positive_under_interval'} or labels == {'negative_under_interval'}
    return {'schema_version': 1,
            'analysis_status': 'hypothetical_range_sensitivity_not_video_verified',
            'scenario_id': s['scenario_id'], 'pot_before_call_bb': p,
            'call_cost_bb': c, 'break_even_equity': round(c / (p + c), 8),
            'range_results': rows, 'range_sensitive': not robust,
            'conclusion': ('consistent_direction_across_supplied_ranges_only' if robust
                           else 'insufficient_robustness_across_supplied_ranges'),
            'source_hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
            'warning': ('Hypothetical heads-up showdown call only. Confidence intervals '
                        'are conditional on supplied ranges, not model uncertainty. '
                        'Not GTO; no diagnosis of actual video decisions.')}

def run(input_path, output_path):
    src, out = Path(input_path), Path(output_path)
    require(src.is_file() and not src.is_symlink() and
            0 < src.stat().st_size <= 65536, 'invalid source')
    require(out.suffix == '.json' and out.parent.is_dir() and
            not out.parent.is_symlink() and not out.exists() and
            not out.is_symlink() and out.resolve() != src.resolve(),
            'output must be a new JSON')
    original = sha(src)
    data = json.loads(src.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    result = compute(data)
    require(sha(src) == original, 'input changed during processing')
    result['source_scenario_sha256'] = original
    with tempfile.TemporaryDirectory(prefix='.plo_call_sensitivity_', dir=out.parent) as d:
        staged = Path(d) / 'result.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n', 'utf-8')
        os.link(staged, out)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('hypothetical_scenario_json')
    p.add_argument('new_output_json')
    a = p.parse_args()
    print(json.dumps({'status': run(a.hypothetical_scenario_json,
                                     a.new_output_json)['analysis_status']}))

if __name__ == '__main__':
    main()
