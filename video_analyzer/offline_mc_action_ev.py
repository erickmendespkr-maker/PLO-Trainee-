"""Offline, *conditional* single-decision EV estimates for reviewed PLO5/PLO6 hands.

Only accepts a separately transcribed scenario linked to an UNVERIFIED visual
summary. Recomputes showdown equity from that scenario; never trusts a supplied
equity value or promotes OCR/reviewer declarations into facts.

Model: chip EV relative to the decision point, zero rake, no future betting,
no side pots, no further opponent contributions for a call. A raise is only
modeled heads-up, with explicit independent fold probability and conditional
called equity assumptions; no range-updating is inferred automatically.

Usage: python offline_mc_action_ev.py SUMMARY.json SCENARIO.json ACTIONS.json NEW_RESULT.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import offline_mc_input_contract as contract
import offline_mc_equity as equity_engine

MODEL = 'single_decision_showdown_no_future_betting_zero_rake'


def finite_fraction(value, label):
    contract.check(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                   f'{label}: expected finite fraction in [0, 1]')
    return float(value)


def assumptions_text(value, label):
    contract.check(type(value) is str and 20 <= len(value.strip()) <= 2000,
                   f'{label}: explicit assumptions required (20-2000 chars)')
    return value.strip()


def validate_action_model(actions, scenario_sha, validated):
    contract.check(type(actions) is dict and set(actions) == {
        'schema_version', 'source_scenario_sha256', 'model', 'rake',
        'assumptions', 'raise_model'}, 'invalid action model schema')
    contract.check(type(actions['schema_version']) is int and actions['schema_version'] == 1,
                   'invalid action schema version')
    contract.check(actions['source_scenario_sha256'] == scenario_sha,
                   'action scenario provenance mismatch')
    contract.check(actions['model'] == MODEL, 'unsupported EV model')
    contract.check(type(actions['rake']) in (int, float) and math.isfinite(actions['rake'])
                   and actions['rake'] == 0, 'rake must be zero in this limited model')
    assumptions = assumptions_text(actions['assumptions'], 'action')
    raise_model = actions['raise_model']
    if raise_model is None:
        return assumptions, None
    contract.check(len(validated['opponents']) == 1,
                   'raise EV only supported heads-up; multiway side pots not modeled')
    contract.check(type(raise_model) is dict and set(raise_model) == {
        'raise_total', 'fold_probability', 'called_equity_fraction',
        'opponent_can_match_raise', 'assumptions'}, 'invalid raise model schema')
    total = contract.positive_money(raise_model['raise_total'], 'raise_total')
    to_call = validated['to_call']
    contract.check(total > to_call and total <= validated['effective_stack'],
                   'raise_total must exceed to_call and fit effective stack')
    contract.check(raise_model['opponent_can_match_raise'] is True,
                   'opponent stack coverage must be explicitly assumed')
    fold_probability = finite_fraction(raise_model['fold_probability'], 'fold_probability')
    called_equity = finite_fraction(raise_model['called_equity_fraction'], 'called_equity_fraction')
    raise_assumptions = assumptions_text(raise_model['assumptions'], 'raise')
    return assumptions, {'raise_total': total, 'fold_probability': fold_probability,
                         'called_equity_fraction': called_equity,
                         'opponent_can_match_raise': True,
                         'assumptions': raise_assumptions}


def calculate(validated, equity_result, actions, scenario_sha):
    """Calculate decision-point chip EV. Equity result must be freshly computed.

    This function is internal; the CLI always rebuilds the validated scenario and
    recomputes equity before calling it. The equity result is not an input file.
    """
    assumptions, raise_model = validate_action_model(actions, scenario_sha, validated)
    contract.check(equity_result['status'] == 'conditional_showdown_equity_estimated_not_ev'
                   and equity_result['hand_id'] == validated['hand_id']
                   and equity_result['table_id'] == validated['table_id']
                   and equity_result['variant'] == validated['variant']
                   and equity_result['seed'] == validated['seed']
                   and equity_result['simulations'] == validated['simulations']
                   and equity_result['automatic_ocr_math_authorization'] is False,
                   'equity provenance mismatch')
    e = finite_fraction(equity_result['equity_fraction'], 'equity')
    lo, hi = equity_result['confidence_interval_95_approx']
    lo = finite_fraction(lo, 'lower confidence limit')
    hi = finite_fraction(hi, 'upper confidence limit')
    contract.check(lo <= e <= hi, 'invalid equity confidence interval')
    pot = validated['pot_before_call']
    call = validated['to_call']
    # Existing pot P includes all bets before hero acts. Hero adds C only.
    # Win relative to this decision = +P; loss = -C.
    def call_ev(x):
        return x * (pot + call) - call
    ev_call = call_ev(e)
    ev_raise = None
    if raise_model is not None:
        r = raise_model['raise_total']
        f = raise_model['fold_probability']
        ec = raise_model['called_equity_fraction']
        # Opponent has already committed C, and calls the extra R-C.
        # On fold hero wins existing pot P. On call, net win is P+(R-C),
        # net loss is R. No rake, further action, or side pots.
        extra = r - call
        called_ev = ec * (pot + r + extra) - r
        ev_raise = {
            'ev_chips': f * pot + (1 - f) * called_ev,
            'opponent_extra_call_chips': extra,
            'ev_if_called_chips': called_ev,
            'fold_probability_assumed': f,
            'called_equity_fraction_assumed_not_simulated': ec,
            'raise_total_chips': r,
            'confidence_interval_95': None,
            'confidence_note': 'No statistical interval: called equity and fold probability are independent manual assumptions.',
            'opponent_can_match_raise_assumed': True,
            'assumptions': raise_model['assumptions'],
        }
    return {
        'schema_version': 1,
        'status': 'conditional_chip_ev_estimates_not_strategy_verdict',
        'hand_id': validated['hand_id'], 'table_id': validated['table_id'],
        'variant': validated['variant'], 'street': validated['street'],
        'source_summary_sha256': validated['source_summary_sha256'],
        'source_video_sha256_claim': validated['source_video_sha256_claim'],
        'source_scenario_sha256': scenario_sha,
        'input_origin_claim': 'independent_manual_transcription_not_authenticated',
        'automatic_ocr_math_authorization': False,
        'model': MODEL, 'rake_chips': 0,
        'pot_before_action_chips': pot, 'to_call_chips': call,
        'effective_stack_chips': validated['effective_stack'],
        'ev_fold_chips': 0.0,
        'ev_call_or_check_chips': ev_call,
        'call_action_label': 'check' if call == 0 else 'call',
        'ev_call_or_check_confidence_interval_95_approx_chips': [call_ev(lo), call_ev(hi)],
        'ev_raise_model': ev_raise,
        'equity_fraction': e,
        'equity_confidence_interval_95_approx': [lo, hi],
        'equity_confidence_method': equity_result['confidence_method'],
        'seed': validated['seed'], 'simulations': validated['simulations'],
        'range_names': equity_result['range_names'],
        'scenario_assumptions': validated['assumptions'],
        'action_assumptions': assumptions,
        'equity_calculated': True, 'ev_calculated': True,
        'warning': ('Chip EV conditional on assumed cards, ranges, pot and simplified future actions. '
                    'No rake, future betting, side pots, opponent range response or visual truth verified. '
                    'Call interval covers Monte Carlo noise only; not range/model uncertainty. '
                    'Raise assumptions are not inferred from Monte Carlo. No definitive poker error verdict.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary_json')
    parser.add_argument('scenario_json')
    parser.add_argument('actions_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    a, b, c, target = map(Path, (args.summary_json, args.scenario_json,
                                args.actions_json, args.new_output_json))
    inputs = (a, b, c)
    contract.check(target.suffix == '.json' and target.parent.is_dir()
                   and not target.parent.is_symlink() and not target.exists()
                   and not target.is_symlink() and len({p.resolve() for p in inputs + (target,)}) == 4,
                   'output must be new and distinct')
    before = tuple(contract.sha256(p) for p in inputs)
    validated = contract.build(contract.read_json(a), contract.read_json(b), before[0])
    actions = contract.read_json(c)
    # Reject invalid action assumptions before costly Monte Carlo.
    validate_action_model(actions, before[1], validated)
    equity_result = equity_engine.compute(validated)
    result = calculate(validated, equity_result, actions, before[1])
    contract.check(before == tuple(contract.sha256(p) for p in inputs),
                   'input changed during action EV computation')
    result['source_action_sha256'] = before[2]
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'ev_call_or_check_chips': result['ev_call_or_check_chips'],
                      'ev_raise_modeled': result['ev_raise_model'] is not None}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
