"""Offline, *conditional* call/fold EV from external heads-up Monte Carlo counts.

This module DOES NOT run or validate a poker engine. It refuses unsupported
models and labels supplied MC outcomes unverified. It does not recommend a bet.
It expects a timestamp-scoped candidate from offline_math_decision_snapshot.

Usage: python offline_call_ev_from_counts.py CANDIDATE.json OUTCOMES.json NEW_REPORT.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

import offline_math_input_gate as gate
import offline_math_decision_snapshot as snapshot

OUTCOME_STATUS = 'external_monte_carlo_outcomes_unverified'
REPORT_STATUS = 'conditional_call_ev_from_unverified_mc_outcomes'
SAMPLING = 'uniform_valid_opponent_combos_and_uniform_remaining_runouts'
OUTCOME_KEYS = {'schema_version', 'status', 'source_candidate_sha256', 'variant',
                'seed', 'trials', 'wins', 'ties', 'losses', 'sampling',
                'omaha_exact_two_hole_three_board'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def build(candidate, outcomes, candidate_sha, outcomes_sha):
    require(type(candidate) is dict and candidate.get('schema_version') == 1 and
            candidate.get('status') == snapshot.STATUS and
            candidate.get('automatic_ocr_math_authorization') is False and
            candidate.get('variant') in ('PLO5', 'PLO6') and
            candidate.get('model') == 'heads_up_call_all_in_no_future_betting_no_rake' and
            candidate.get('decision_street') in snapshot.STREETS and
            type(candidate.get('board')) is list and
            len(candidate['board']) == snapshot.EXPECTED_BOARD[candidate['decision_street']] and
            type(candidate.get('villain_combos')) is list and
            len(candidate['villain_combos']) >= 1,
            'unsupported or unscoped candidate')
    require(type(outcomes) is dict and set(outcomes) == OUTCOME_KEYS and
            outcomes['schema_version'] == 1 and
            outcomes['status'] == OUTCOME_STATUS and
            outcomes['source_candidate_sha256'] == candidate_sha and
            outcomes['variant'] == candidate['variant'] and
            outcomes['sampling'] == SAMPLING and
            outcomes['omaha_exact_two_hole_three_board'] is True,
            'unsupported or unbound external simulation')
    seed, n = candidate.get('seed'), candidate.get('trials')
    require(type(seed) is int and type(n) is int and
            0 <= seed < 2**63 and 100 <= n <= 100000 and
            type(outcomes['seed']) is int and outcomes['seed'] == seed and
            type(outcomes['trials']) is int and outcomes['trials'] == n,
            'simulation seed/trials mismatch')
    counts = [outcomes[k] for k in ('wins', 'ties', 'losses')]
    require(all(type(v) is int and v >= 0 for v in counts) and sum(counts) == n,
            'invalid outcome counts')
    weights = [x.get('weight') for x in candidate['villain_combos']
               if type(x) is dict]
    require(len(weights) == len(candidate['villain_combos']) and
            all(type(w) in (int, float) and math.isfinite(w) and w > 0 for w in weights) and
            all(w == weights[0] for w in weights),
            'nonuniform opponent weights require a weighted sampler')
    p, c = candidate.get('pot_before_call'), candidate.get('to_call')
    require(type(p) in (int, float) and type(c) in (int, float) and
            math.isfinite(p) and math.isfinite(c) and 0 < c <= p <= 1e12,
            'invalid pot/call')
    # HU split-pot outcome pays 1/2, win pays 1, loss pays 0.
    q = (counts[0] + 0.5 * counts[1]) / n
    # Hoeffding's two-sided 95% bound for iid outcomes in [0,1].
    # Conditional on valid independent draws from the declared sampling model.
    radius = math.sqrt(math.log(2 / .05) / (2 * n))
    lower, upper = max(0.0, q - radius), min(1.0, q + radius)
    total = p + c
    return {'schema_version': 1, 'status': REPORT_STATUS,
            'variant': candidate['variant'],
            'table_id': candidate.get('table_id'), 'hand_id': candidate.get('hand_id'),
            'decision_timestamp_seconds': candidate.get('decision_timestamp_seconds'),
            'decision_street': candidate['decision_street'],
            'model': candidate['model'], 'seed': seed, 'trials': n,
            'wins': counts[0], 'ties': counts[1], 'losses': counts[2],
            'equity_estimate': q,
            'equity_95pct_hoeffding_interval': [lower, upper],
            'ev_fold': 0.0,
            'ev_call_estimate': q * total - c,
            'ev_call_95pct_hoeffding_interval': [lower * total - c,
                                                  upper * total - c],
            'break_even_equity': c / total,
            'source_candidate_sha256': candidate_sha,
            'source_external_outcomes_sha256': outcomes_sha,
            'confidence_assumption': '95% Hoeffding bound requires iid valid outcome samples; external engine not independently validated.',
            'range_assumption': 'Uniform opponent combo selection and uniform legal runouts; hypothetical manually supplied range.',
            'warning': 'Conditional arithmetic only, not a verified poker simulation or definitive strategy verdict.'}


def run(candidate_path, outcomes_path, output_path):
    candidate_path, outcomes_path, output_path = map(Path,
        (candidate_path, outcomes_path, output_path))
    require(len({p.resolve() for p in (candidate_path, outcomes_path, output_path)}) == 3,
            'input/output paths must differ')
    require(output_path.parent.is_dir() and not output_path.parent.is_symlink() and
            not output_path.exists() and not output_path.is_symlink(),
            'unsafe output')
    csha, osha = gate.digest(candidate_path), gate.digest(outcomes_path)
    result = build(gate.load(candidate_path), gate.load(outcomes_path), csha, osha)
    require(gate.digest(candidate_path) == csha and
            gate.digest(outcomes_path) == osha, 'source changed')
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=output_path.parent,
                                         prefix='.plo_ev_', suffix='.tmp', delete=False) as f:
            temp_name = f.name
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        require(not output_path.exists() and not output_path.is_symlink(),
                'output collision')
        os.link(temp_name, output_path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate_json')
    p.add_argument('external_outcomes_json')
    p.add_argument('new_report_json')
    a = p.parse_args()
    print(run(a.candidate_json, a.external_outcomes_json,
              a.new_report_json)['status'])
