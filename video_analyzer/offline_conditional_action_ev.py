"""Offline *hypothetical* fold/call/raise EV for manually reviewed PLO5/PLO6.

This is a one-opponent, terminal-showdown model, NOT a grade of an observed
poker action. Both conditional opponent ranges and the probability of a fold
are supplied by the reviewer; they are not inferred from video or OCR.

Usage: python offline_conditional_action_ev.py INPUT.json NEW_OUTPUT.json
No network, live play, rake, side pots, or future betting are modeled.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from offline_plo_equity_monte_carlo import analyze, read_json, require


def _finite(value, name, *, minimum=0.0, maximum=1_000_000_000.0):
    require(type(value) in (float, int) and math.isfinite(value) and
            minimum <= value <= maximum, f'invalid {name}')
    return float(value)


def _scenario(value, name):
    require(type(value) is dict, f'{name} must be an object')
    require('pot_now' not in value and 'call_cost' not in value,
            f'{name} cannot contain separate pot parameters')
    require(value.get('manual_review_confirmed') is True,
            f'{name} requires explicit human review')
    return analyze(value)


def build(data):
    require(type(data) is dict and set(data) == {
        'call_scenario', 'raise_called_scenario', 'pot_now', 'call_cost',
        'raise_extra', 'fold_probability_assumed'
    }, 'invalid EV input schema')
    pot = _finite(data['pot_now'], 'pot_now', minimum=0.000001)
    cost = _finite(data['call_cost'], 'call_cost', minimum=0.000001)
    extra = _finite(data['raise_extra'], 'raise_extra', minimum=0.000001)
    fold_p = _finite(data['fold_probability_assumed'], 'fold_probability_assumed', maximum=1.0)
    require(pot >= cost, 'pot_now must include the opponent bet being called')
    require(cost + extra <= 1_000_000_000 and pot + cost + 2*extra <= 1_000_000_000,
            'unbounded final pot')

    call = _scenario(data['call_scenario'], 'call_scenario')
    raised = _scenario(data['raise_called_scenario'], 'raise_called_scenario')
    for field in ('variant', 'hero_cards', 'board_cards'):
        require(call[field] == raised[field], f'{field} mismatch between scenarios')
    require(call['ocr_semantics_verified'] is False and raised['ocr_semantics_verified'] is False and
            call['strategic_correctness_verified'] is False and
            raised['strategic_correctness_verified'] is False,
            'unsafe verification status')

    call_final_pot = pot + cost
    raise_commit = cost + extra
    # Villain has already bet 'cost' into pot_now. If they call a raise,
    # they add precisely 'extra'. No all-in/side-pot asymmetry is modeled.
    raise_final_pot = pot + raise_commit + extra
    call_ev = call['equity'] * call_final_pot - cost
    called_raise_ev = raised['equity'] * raise_final_pot - raise_commit
    raise_ev = fold_p*pot + (1-fold_p)*called_raise_ev
    call_ci = [v*call_final_pot-cost for v in call['equity_ci95_sampling_only']]
    raise_ci = [fold_p*pot + (1-fold_p)*(v*raise_final_pot-raise_commit)
                for v in raised['equity_ci95_sampling_only']]
    # This comparison interval is a conservative interval combination, not
    # a calibrated 95% joint confidence interval for EV difference.
    diff_bounds = [raise_ci[0]-call_ci[1], raise_ci[1]-call_ci[0]]
    # Raise EV equals call EV when p*(pot - called_raise_ev) = call_ev - called_raise_ev.
    denominator = pot-called_raise_ev
    threshold = None if abs(denominator) < 1e-12 else (call_ev-called_raise_ev)/denominator
    return {
        'schema_version': 1,
        'analysis_status': 'offline_hypothetical_terminal_action_ev_not_a_grade',
        'variant': call['variant'],
        'hero_cards': call['hero_cards'], 'board_cards': call['board_cards'],
        'pot_now_including_opponent_bet': pot, 'hero_call_cost': cost,
        'hero_raise_extra_above_call': extra, 'opponent_extra_call_if_raise_called': extra,
        'fold_probability_assumed': fold_p,
        'fold_ev_incremental': 0.0,
        'call_ev_incremental': call_ev,
        'raise_ev_incremental': raise_ev,
        'raise_ev_minus_call_ev': raise_ev-call_ev,
        'call_ev_ci95_sampling_only': call_ci,
        'raise_ev_ci95_sampling_only_fixed_fold_probability': raise_ci,
        'raise_minus_call_interval_from_marginal_bounds_not_joint_ci': diff_bounds,
        'fold_probability_where_raise_equals_call_unclipped': threshold,
        'call_scenario_equity': call,
        'raise_called_scenario_equity': raised,
        'range_models_are_reviewer_assumptions': True,
        'fold_probability_is_reviewer_assumption': True,
        'action_observed_or_graded': False,
        'hero_identity_verified': False,
        'ocr_semantics_verified': False,
        'model_assumptions': [
            'Heads-up only; one opponent; no rake, side pots, all-ins, or future betting.',
            'pot_now includes the opponent bet before hero acts; fold EV is zero incremental.',
            'Call equity uses call_scenario opponent range; raise-called equity uses a separate conditional range.',
            'Raise extra is matched exactly by the opponent when called; no short calls.',
            'Fold probability and both ranges are assumptions, not estimated from video.',
            'Monte Carlo confidence intervals only measure sampling uncertainty with ranges and fold probability fixed.',
        ],
        'warning': ('Illustrative conditional EV, not advice or an assessment of an observed action. '
                    'Missing action attribution, opponent behavior, future betting and range uncertainty '
                    'can dominate Monte Carlo sampling error.')
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_input_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    source = Path(args.reviewed_input_json)
    target = Path(args.new_output_json)
    require(target.suffix == '.json' and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink() and source.resolve() != target.resolve(),
            'output must be a new JSON file distinct from input')
    result = build(read_json(source))
    with target.open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'call_ev': result['call_ev_incremental'],
                      'raise_ev': result['raise_ev_incremental'],
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
