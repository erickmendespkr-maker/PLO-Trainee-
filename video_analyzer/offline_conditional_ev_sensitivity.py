"""Offline sensitivity of hypothetical PLO5/PLO6 EV to fold probability/range.

No opponent inference, OCR verification, observed-action grading or live play.
Each named range hypothesis is independently sampled once via the existing
Monte Carlo EV engine. The fold-probability grid is evaluated analytically,
without falsely treating the grid cells as independent simulations.

CLI: python offline_conditional_ev_sensitivity.py INPUT.json NEW_OUTPUT.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from offline_conditional_action_ev import build as build_ev
from offline_plo_equity_monte_carlo import read_json, require


def _probability(x):
    require(type(x) in (float, int) and math.isfinite(x) and 0 <= x <= 1,
            'fold probability must be a finite number between zero and one')
    return float(x)


def build(data):
    require(type(data) is dict and set(data) == {'hypotheses', 'fold_probabilities'},
            'invalid sensitivity input schema')
    hypotheses, probabilities = data['hypotheses'], data['fold_probabilities']
    require(type(hypotheses) is list and 1 <= len(hypotheses) <= 5,
            'provide one to five range hypotheses')
    require(type(probabilities) is list and 2 <= len(probabilities) <= 21,
            'provide two to 21 fold probabilities')
    probabilities = [_probability(p) for p in probabilities]
    require(all(a < b for a, b in zip(probabilities, probabilities[1:])),
            'fold probabilities must be strictly increasing')
    rows = []
    seen = set()
    common = None
    for item in hypotheses:
        require(type(item) is dict and set(item) == {'label', 'ev_input'},
                'invalid hypothesis schema')
        label = item['label']
        require(type(label) is str and 1 <= len(label) <= 64 and
                all(c.isprintable() and c not in '<>\\' for c in label),
                'invalid hypothesis label')
        require(label not in seen, 'duplicate hypothesis label')
        seen.add(label)
        ev = build_ev(item['ev_input'])
        require(ev['action_observed_or_graded'] is False and
                ev['ocr_semantics_verified'] is False and
                ev['hero_identity_verified'] is False, 'unsafe EV status')
        signature = (ev['variant'], tuple(ev['hero_cards']), tuple(ev['board_cards']),
                     ev['pot_now_including_opponent_bet'], ev['hero_call_cost'],
                     ev['hero_raise_extra_above_call'])
        if common is None:
            common = signature
        require(signature == common,
                'all hypotheses must use the same hand and pot parameters')
        pot = ev['pot_now_including_opponent_bet']
        cost = ev['hero_call_cost']
        extra = ev['hero_raise_extra_above_call']
        final_pot = pot + cost + 2*extra
        commit = cost + extra
        equity = ev['raise_called_scenario_equity']['equity']
        ci = ev['raise_called_scenario_equity']['equity_ci95_sampling_only']
        called_ev = equity*final_pot - commit
        called_ci = [v*final_pot-commit for v in ci]
        call_ev = ev['call_ev_incremental']
        call_ci = ev['call_ev_ci95_sampling_only']
        points = []
        for p in probabilities:
            raise_ev = p*pot + (1-p)*called_ev
            bounds = [p*pot + (1-p)*v for v in called_ci]
            points.append({
                'fold_probability_assumed': p,
                'fold_ev_incremental': 0.0,
                'call_ev_incremental': call_ev,
                'raise_ev_incremental': raise_ev,
                'raise_minus_call_ev': raise_ev-call_ev,
                'raise_ev_ci95_sampling_only_fixed_ranges_and_fold_probability': bounds,
                'raise_minus_call_bounds_from_marginals_not_joint_ci':
                    [bounds[0]-call_ci[1], bounds[1]-call_ci[0]],
            })
        rows.append({
            'label': label,
            'call_range_model': ev['call_scenario_equity']['opponent_model_kind'],
            'raise_called_range_model': ev['raise_called_scenario_equity']['opponent_model_kind'],
            'call_equity': ev['call_scenario_equity']['equity'],
            'raise_called_equity': equity,
            'call_iterations': ev['call_scenario_equity']['iterations'],
            'raise_called_iterations': ev['raise_called_scenario_equity']['iterations'],
            'call_seed': ev['call_scenario_equity']['seed'],
            'raise_called_seed': ev['raise_called_scenario_equity']['seed'],
            'baseline_fold_probability_assumed': ev['fold_probability_assumed'],
            'break_even_fold_probability_unclipped':
                ev['fold_probability_where_raise_equals_call_unclipped'],
            'points': points,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'offline_hypothetical_ev_sensitivity_not_an_action_grade',
        'variant': common[0], 'hero_cards': list(common[1]),
        'board_cards': list(common[2]),
        'pot_now_including_opponent_bet': common[3],
        'hero_call_cost': common[4], 'hero_raise_extra_above_call': common[5],
        'fold_probabilities': probabilities,
        'hypotheses': rows,
        'range_models_are_reviewer_assumptions': True,
        'fold_probabilities_are_assumptions': True,
        'action_observed_or_graded': False,
        'ocr_semantics_verified': False,
        'hero_identity_verified': False,
        'confidence_intervals_cover_sampling_only': True,
        'warning': ('Illustrative heads-up terminal EV only; no rake, side pots, all-ins or future betting. '
                    'No video inference or action grading. Fold probabilities and opponent ranges '
                    'are hypotheses, not empirical confidence intervals. Differences between '
                    'hypotheses reflect model sensitivity, not measured uncertainty. Monte Carlo '
                    'intervals are marginal sampling bounds, not joint 95% EV-difference intervals.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    src, dst = Path(args.input_json), Path(args.new_output_json)
    require(dst.suffix == '.json' and dst.parent.is_dir() and
            not dst.parent.is_symlink() and not dst.exists() and
            not dst.is_symlink() and dst.resolve() != src.resolve(),
            'output must be a new JSON file distinct from input')
    result = build(read_json(src))
    with dst.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'hypotheses': len(result['hypotheses']),
                      'fold_probability_points': len(result['fold_probabilities']),
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
