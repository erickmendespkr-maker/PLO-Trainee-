"""Offline PLO5/PLO6 reviewed-decision -> existing Omaha MC -> conditional call EV.

Fail closed: only timestamp-scoped, human-reviewed candidates, explicit *uniform*
legal opponent combos and heads-up terminal-showdown call model. Never reads
video or poker clients. Range/model/visual uncertainty is NOT captured by CI.
Usage: python offline_math_mc_bridge.py CANDIDATE.json NEW_REPORT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

import offline_math_input_gate as gate
import offline_math_decision_snapshot as snapshot
import offline_call_ev_from_counts as ev
import offline_omaha_equity_mc as mc

STATUS = 'offline_internal_mc_conditional_call_ev_not_strategy_verdict'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def scenario_from_candidate(c):
    require(type(c) is dict and c.get('schema_version') == 1 and
            c.get('status') == snapshot.STATUS and
            c.get('automatic_ocr_math_authorization') is False and
            c.get('variant') in ('PLO5', 'PLO6') and
            c.get('model') == 'heads_up_call_all_in_no_future_betting_no_rake',
            'unsupported or unreviewed decision candidate')
    street = c.get('decision_street')
    require(type(street) is str and street in snapshot.EXPECTED_BOARD,
            'invalid decision street')
    t = c.get('decision_timestamp_seconds')
    require(type(t) in (int, float) and math.isfinite(t) and t >= 0,
            'invalid decision timestamp')
    count = 5 if c['variant'] == 'PLO5' else 6
    hero = gate.cards(c.get('hero_cards'), count, 'hero')
    board = c.get('board')
    require(type(board) is list and len(board) == snapshot.EXPECTED_BOARD[street],
            'board/street mismatch')
    board = gate.cards(board, len(board), 'board')
    require(not set(hero).intersection(board) and
            type(c.get('decision_board_cards')) is int and
            c['decision_board_cards'] == len(board), 'invalid board evidence')
    for key in ('source_review_sha256', 'source_assumptions_sha256'):
        require(type(c.get(key)) is str and HEX64.fullmatch(c[key]),
                'missing source hash: ' + key)
    require(c.get('source_full_review_sha256') == c['source_review_sha256'] and
            c.get('source_full_assumptions_sha256') == c['source_assumptions_sha256'],
            'source provenance mismatch')
    require(type(c.get('range_source')) is str and
            8 <= len(c['range_source'].strip()) <= 300 and
            type(c.get('confidence_note')) is str and
            len(c['confidence_note'].strip()) >= 8,
            'range provenance and confidence disclosure required')
    require(type(c.get('table_id')) is str and c['table_id'].strip() and
            type(c.get('hand_id')) is str and c['hand_id'].strip(),
            'missing table/hand identity')
    seed, trials = c.get('seed'), c.get('trials')
    require(type(seed) is int and 0 <= seed < 2**32 and
            type(trials) is int and 100 <= trials <= mc.MAX_SAMPLES,
            'MC parameters outside existing engine limits')
    pot, call = c.get('pot_before_call'), c.get('to_call')
    gate.numeric(pot, 0, 1e12, 'pot')
    gate.numeric(call, 0, 1e12, 'call')
    require(0 < call <= pot, 'invalid call/pot relationship')
    combos = c.get('villain_combos')
    require(type(combos) is list and 1 <= len(combos) <= mc.MAX_RANGE,
            'opponent range outside existing engine limits')
    valid, seen, weights = [], set(), []
    for entry in combos:
        require(type(entry) is dict and set(entry) == {'cards', 'weight'},
                'invalid opponent range entry')
        hole = gate.cards(entry['cards'], count, 'villain')
        require(not (set(hole) & (set(hero) | set(board))),
                'opponent cards overlap known cards')
        canonical = tuple(sorted(hole))
        require(canonical not in seen, 'duplicate opponent combination')
        seen.add(canonical)
        weight = gate.numeric(entry['weight'], 0, 1e6, 'weight')
        require(weight > 0, 'zero-weight range entry')
        weights.append(weight)
        valid.append(hole)
    require(all(w == weights[0] for w in weights),
            'weighted opponent ranges require a different sampler')
    return {'schema_version': 1, 'game_type': c['variant'],
            'hero_hole': hero, 'known_board': board,
            'explicit_villain_hands': valid, 'samples': trials, 'seed': seed,
            'range_assumption': c['range_source']}


def build(candidate, candidate_sha):
    require(type(candidate_sha) is str and HEX64.fullmatch(candidate_sha),
            'invalid candidate SHA-256')
    scenario = scenario_from_candidate(candidate)
    mc_result = mc.estimate(scenario)
    n = scenario['samples']
    require(type(mc_result) is dict and
            mc_result.get('analysis_status') == 'conditional_heads_up_equity_only' and
            mc_result.get('game_type') == scenario['game_type'] and
            mc_result.get('hero_hole') == scenario['hero_hole'] and
            mc_result.get('known_board') == scenario['known_board'] and
            mc_result.get('seed') == scenario['seed'] and
            mc_result.get('samples') == n and
            mc_result.get('exactly_two_private_three_board') is True and
            mc_result.get('video_evidence_verified') is False and
            mc_result.get('opponent_range_weighting') == 'uniform_over_unblocked_explicit_combinations' and
            mc_result.get('eligible_opponent_combinations') == len(scenario['explicit_villain_hands']) and
            mc_result.get('blocked_opponent_combinations') == 0,
            'unexpected engine result')
    counts = [mc_result.get(k) for k in ('wins', 'ties', 'losses')]
    require(all(type(x) is int and x >= 0 for x in counts) and sum(counts) == n,
            'engine counts invalid')
    q = (counts[0] + 0.5 * counts[1]) / n
    require(type(mc_result.get('equity_estimate')) in (float, int) and
            math.isclose(mc_result['equity_estimate'], q, abs_tol=1e-12),
            'engine equity/count mismatch')
    outcomes = {'schema_version': 1, 'status': ev.OUTCOME_STATUS,
                'source_candidate_sha256': candidate_sha,
                'variant': candidate['variant'], 'seed': scenario['seed'],
                'trials': n, 'wins': counts[0], 'ties': counts[1],
                'losses': counts[2], 'sampling': ev.SAMPLING,
                'omaha_exact_two_hole_three_board': True}
    outcomes_bytes = json.dumps(outcomes, sort_keys=True, separators=(',', ':'),
                                allow_nan=False).encode('utf-8')
    outcomes_sha = hashlib.sha256(outcomes_bytes).hexdigest()
    report = ev.build(candidate, outcomes, candidate_sha, outcomes_sha)
    report['status'] = STATUS
    report['source_internal_mc_outcomes_sha256'] = report.pop('source_external_outcomes_sha256')
    report['mc_engine'] = 'offline_omaha_equity_mc.estimate'
    report['mc_engine_status'] = mc_result['analysis_status']
    report['mc_engine_range_eligible_combos'] = mc_result['eligible_opponent_combinations']
    report['mc_engine_rule_exact_two_hole_three_board'] = True
    report['source_review_sha256_claim'] = candidate['source_review_sha256']
    report['source_assumptions_sha256_claim'] = candidate['source_assumptions_sha256']
    report['confidence_assumption'] = ('95% Hoeffding interval covers independent Monte Carlo '
        'sampling conditional on manually asserted cards and uniform range only; '
        'not OCR, opponent range accuracy, future betting or model uncertainty.')
    report['warning'] = ('Existing offline Omaha MC executed on a human-reviewed decision '
        'candidate; original video and human attestation were not independently verified. '
        'Heads-up all-in terminal-showdown call EV only; no strategy verdict.')
    report['automatic_clip_selection_authorized'] = False
    report['strategic_correctness_verified'] = False
    return report


def run(candidate_path, output_path):
    source, dest = Path(candidate_path), Path(output_path)
    require(source.resolve() != dest.resolve() and dest.suffix == '.json' and
            dest.parent.is_dir() and not dest.parent.is_symlink() and
            not dest.exists() and not dest.is_symlink(), 'unsafe output path')
    before = gate.digest(source)
    report = build(gate.load(source), before)
    require(gate.digest(source) == before, 'candidate changed during simulation')
    staged = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=dest.parent,
                                         prefix='.plo_mc_bridge_', suffix='.tmp',
                                         delete=False) as f:
            staged = f.name
            json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
        require(not dest.exists() and not dest.is_symlink(), 'output collision')
        os.link(staged, dest)
    finally:
        if staged and os.path.exists(staged):
            os.unlink(staged)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('timestamped_candidate_json')
    p.add_argument('new_report_json')
    a = p.parse_args()
    print(run(a.timestamped_candidate_json, a.new_report_json)['status'])
