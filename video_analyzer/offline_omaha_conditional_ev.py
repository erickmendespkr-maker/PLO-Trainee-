"""Offline PLO5/PLO6 heads-up *terminal-showdown* EV sensitivity model.

Not a recommendation, a betting-legality checker, or a live-poker tool.
Both opponent ranges and fold probability are explicit hypotheses. The model
recomputes Monte Carlo equity for calling and for a raise *when called*;
these can be different ranges. It assumes zero rake, no side pots and no
future betting. Pot is the amount visible BEFORE the hero acts, including the
opponent's current bet. All EVs are incremental from this decision point.

Usage: python offline_omaha_conditional_ev.py SCENARIO.json NEW_REPORT.json
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import tempfile

import offline_omaha_equity_mc as mc

MAX_BYTES = 512 * 1024
MAX_MONEY = Decimal('1000000000')
ASSUMPTION_KEYS = (
    'heads_up_only', 'terminal_showdown_after_call_or_raise_called',
    'no_side_pots', 'zero_rake', 'pot_includes_opponent_current_bet',
    'ranges_and_fold_probability_are_hypotheses', 'raise_legality_verified',
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def decimal(value, label, *, probability=False):
    require(type(value) in (int, float, str, Decimal), f'{label}: invalid number type')
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label}: invalid decimal') from exc
    require(d.is_finite(), f'{label}: non-finite')
    if probability:
        require(0 <= d <= 1, f'{label}: probability outside [0,1]')
    else:
        require(0 <= d <= MAX_MONEY and d.as_tuple().exponent >= -2,
                f'{label}: amount outside limits or more than 2 decimals')
    return d


def money(d):
    return format(d.quantize(Decimal('0.01')), '.2f')


def probability_bounds(raw, point):
    require(type(raw) is list and len(raw) == 2, 'fold_probability_bounds: two values required')
    lo, hi = (decimal(v, 'fold_probability_bounds', probability=True) for v in raw)
    require(lo <= point <= hi, 'Fold probability must lie within declared bounds')
    return lo, hi


def validated(raw):
    mc.strict_keys(raw, ('schema_version', 'decision_id', 'source_note',
                         'pot_before_decision', 'call_cost', 'raise_total',
                         'fold_probability', 'fold_probability_bounds',
                         'call_scenario', 'raise_called_scenario', 'model_assumptions'))
    require(type(raw['schema_version']) is int and raw['schema_version'] == 1,
            'Unsupported EV schema')
    for key in ('decision_id', 'source_note'):
        require(type(raw[key]) is str and 1 <= len(raw[key].strip()) <= 1000,
                f'{key}: nonempty text required')
    assumptions = raw['model_assumptions']
    mc.strict_keys(assumptions, ASSUMPTION_KEYS)
    for key in ASSUMPTION_KEYS:
        require(type(assumptions[key]) is bool, f'{key}: expected boolean')
        require(assumptions[key] is (key != 'raise_legality_verified'),
                f'{key}: model cannot support this assumption')
    pot = decimal(raw['pot_before_decision'], 'pot_before_decision')
    call = decimal(raw['call_cost'], 'call_cost')
    raise_total = decimal(raw['raise_total'], 'raise_total')
    require(pot > 0 and 0 < call <= pot, 'Call must be positive and included in pot')
    require(call < raise_total <= pot + 2 * call,
            'Raise outside conservative heads-up pot-limit bound')
    fold = decimal(raw['fold_probability'], 'fold_probability', probability=True)
    fold_bounds = probability_bounds(raw['fold_probability_bounds'], fold)
    a = mc.validate_scenario(raw['call_scenario'])
    b = mc.validate_scenario(raw['raise_called_scenario'])
    require(a['game_type'] == b['game_type'] and a['hero_hole'] == b['hero_hole'] and
            a['known_board'] == b['known_board'],
            'Call and raise-called scenarios must describe the same visible snapshot')
    return pot, call, raise_total, fold, fold_bounds


def calculate(raw):
    pot, call, raise_total, fold, (fold_low, fold_high) = validated(raw)
    call_mc = mc.estimate(raw['call_scenario'])
    raise_mc = mc.estimate(raw['raise_called_scenario'])
    eq_call = Decimal(str(call_mc['equity_estimate']))
    eq_raise = Decimal(str(raise_mc['equity_estimate']))
    c_lo, c_hi = map(lambda x: Decimal(str(x)), call_mc['equity_95pct_hoeffding_interval'])
    r_lo, r_hi = map(lambda x: Decimal(str(x)), raise_mc['equity_95pct_hoeffding_interval'])
    # Heads-up raise: hero adds raise_total; villain adds raise_total - call_cost.
    # No future action or rake; folds win the pot that existed before the decision.
    raise_called_pot = pot + raise_total + (raise_total - call)
    call_pot = pot + call
    call_ev = lambda e: e * call_pot - call
    called_raise_ev = lambda e: e * raise_called_pot - raise_total
    raise_ev = lambda e, f: f * pot + (Decimal(1) - f) * called_raise_ev(e)
    raise_corners = [raise_ev(e, f) for e in (r_lo, r_hi)
                     for f in (fold_low, fold_high)]
    result = {
        'schema_version': 1,
        'analysis_status': 'hypothetical_heads_up_terminal_showdown_ev_only',
        'decision_id': raw['decision_id'], 'source_note': raw['source_note'],
        'game_type': call_mc['game_type'],
        'incremental_ev_unit': 'same_units_as_pot_and_bets',
        'pot_before_decision': money(pot), 'call_cost': money(call),
        'raise_total': money(raise_total),
        'villain_extra_call_after_raise': money(raise_total - call),
        'fold_probability': str(fold),
        'fold_probability_assumed_bounds': [str(fold_low), str(fold_high)],
        'ev_fold': '0.00',
        'ev_call': money(call_ev(eq_call)),
        'ev_call_sampling_bounds': [money(call_ev(c_lo)), money(call_ev(c_hi))],
        'ev_raise': money(raise_ev(eq_raise, fold)),
        'ev_raise_sampling_and_fold_assumption_bounds': [money(min(raise_corners)),
                                                         money(max(raise_corners))],
        'call_equity': call_mc,
        'raise_called_equity': raise_mc,
        'model_assumptions': raw['model_assumptions'],
        'model_limitations': [
            'Ranges and fold probability are user hypotheses, not observed facts.',
            'No future betting, multiway action, side pots, rake, or ICM.',
            'Raise legality, stack sufficiency and min-raise are NOT verified.',
            'Fold EV is zero relative to this decision, ignoring sunk costs.',
            'Equity bounds cover Monte Carlo sampling only, conditional on range.',
            'Raise bounds also span the user-supplied fold-probability interval.',
            'No uncertainty guarantee for model misspecification or OCR errors.',
        ],
        'complete_hand_reconstructed': False,
        'video_evidence_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
    }
    return result


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def process(input_path, output_path):
    source, dest = Path(input_path), Path(output_path)
    require(source.is_file() and not source.is_symlink() and
            0 < source.stat().st_size <= MAX_BYTES, 'Invalid input file')
    require(dest.parent.is_dir() and not dest.parent.is_symlink() and
            not dest.exists() and not dest.is_symlink() and
            dest.resolve() != source.resolve(), 'Output must be a new, separate file')
    before = sha(source)
    raw = json.loads(source.read_text(encoding='utf-8'),
                     object_pairs_hook=mc.no_duplicate_json_keys,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    report = calculate(raw)
    require(sha(source) == before, 'Input changed during computation')
    report['source_scenario_sha256'] = before
    with tempfile.TemporaryDirectory(prefix='plo_ev_', dir=dest.parent) as d:
        stage = Path(d) / 'report.json'
        stage.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
        os.link(stage, dest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario')
    parser.add_argument('new_report')
    args = parser.parse_args(argv)
    result = process(args.scenario, args.new_report)
    print(json.dumps({'status': result['analysis_status'], 'ev_call': result['ev_call'],
                      'ev_raise': result['ev_raise']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
