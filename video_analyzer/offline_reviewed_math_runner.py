"""Reproducible offline Monte Carlo for a verified human-reviewed hand queue.

Usage: python offline_reviewed_math_runner.py PLAN.json ANNOTATIONS.json QUEUE.json NEW_DIR

Fail closed: reconstruct the queue from the two source files and compare the
entire JSON object, including its hashes, before running any simulations.
Never infers cards, actions, player identity, or actual strategy correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import offline_reviewed_hand_math_queue as queue
import offline_plo_equity_monte_carlo as equity

MAX_TOTAL_ITERATIONS = 200_000
MAX_ELIGIBLE_HANDS = 20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_inputs(plan_path, annotations_path, queue_path):
    paths = [Path(p) for p in (plan_path, annotations_path, queue_path)]
    require(len({p.resolve() for p in paths}) == 3, 'inputs must be distinct files')
    before = [queue.digest(p) for p in paths]
    plan, annotations, actual = [queue.read(p) for p in paths]
    expected = queue.build(plan, annotations, before[0], before[1])
    require(actual == expected, 'queue does not match reviewed plan and annotations')
    require(actual['source_plan_sha256'] == before[0] and
            actual['source_annotations_sha256'] == before[1], 'source hash mismatch')
    require([queue.digest(p) for p in paths] == before, 'source changed during verification')
    eligible = [e for e in actual['entries'] if e['eligible_for_offline_monte_carlo']]
    require(len(eligible) <= MAX_ELIGIBLE_HANDS, 'too many eligible hands per batch')
    require(sum(e['equity_input']['iterations'] for e in eligible) <= MAX_TOTAL_ITERATIONS,
            'simulation budget exceeded')
    return actual, before


def build_results(validated_queue, source_hashes):
    results = []
    for entry in validated_queue['entries']:
        row = {'hand_id': entry['hand_id'], 'table_id': entry['table_id'],
               'start_seconds': entry['start_seconds'], 'end_seconds': entry['end_seconds'],
               'reviewer_confidence_declared_not_calibrated':
                   entry['reviewer_confidence_declared_not_calibrated']}
        if not entry['eligible_for_offline_monte_carlo']:
            row.update(status='blocked_not_analyzed', blocked_reasons=entry['blocked_reasons'],
                       result_file=None, result_sha256=None)
        else:
            data = entry['equity_input']
            result = equity.analyze(data)
            require(result['iterations'] == data['iterations'] and
                    result['seed'] == data['seed'] and
                    result['variant'] == data['variant'] and
                    result['hero_cards'] == data['hero_cards'] and
                    result['board_cards'] == data['board_cards'] and
                    result['opponent_model_kind'] == data['opponent_model']['kind'] and
                    result['win_count'] + result['tie_count'] + result['loss_count'] ==
                    data['iterations'], 'engine returned inconsistent result')
            filename = 'hands/' + entry['hand_id'] + '.json'
            raw = json_bytes(result)
            row.update(status='offline_conditional_equity_computed',
                       blocked_reasons=[], result_file=filename,
                       result_sha256=sha_bytes(raw),
                       equity_input_sha256=sha_bytes(json_bytes(data)),
                       iterations=result['iterations'], seed=result['seed'],
                       equity=result['equity'],
                       equity_ci95_sampling_only=result['equity_ci95_sampling_only'],
                       terminal_call_ev_model=result.get('terminal_call_ev_model'))
            row['_raw'] = raw
        results.append(row)
    manifest = {'schema_version': 1,
                'status': 'offline_reviewed_conditional_monte_carlo_results',
                'source_video_sha256_claim': validated_queue['source_video_sha256_claim'],
                'source_plan_sha256': source_hashes[0],
                'source_annotations_sha256': source_hashes[1],
                'source_queue_sha256': source_hashes[2],
                'eligible_analyzed_count': sum(r['status'] == 'offline_conditional_equity_computed'
                                               for r in results),
                'blocked_count': sum(r['status'] == 'blocked_not_analyzed' for r in results),
                'total_iterations': sum(r.get('iterations', 0) for r in results),
                'video_or_ocr_verified': False,
                'human_card_claims_independently_verified': False,
                'opponent_ranges_are_assumptions': True,
                'reviewer_confidence_not_calibrated': True,
                'ci95_is_sampling_error_only': True,
                'actions_observed_or_graded': False,
                'terminal_call_ev_is_a_conditional_model_not_realized_ev': True,
                'warning': 'Offline analysis only. Human card claims and ranges are not verified by the video. No action grading or live assistance.',
                'hands': [{k: v for k, v in r.items() if k != '_raw'} for r in results]}
    return manifest, {r['result_file']: r['_raw'] for r in results if '_raw' in r}


def run(plan_path, annotations_path, queue_path, destination):
    destination = Path(destination)
    parent = destination.parent
    require(parent.is_dir() and not parent.is_symlink() and
            not destination.exists() and not destination.is_symlink() and
            destination.name not in ('', '.', '..'), 'output must be a new directory')
    sources = [Path(p) for p in (plan_path, annotations_path, queue_path)]
    require(destination.resolve() not in {p.resolve() for p in sources},
            'output cannot replace an input')
    verified, hashes = verify_inputs(*sources)
    manifest, files = build_results(verified, hashes)
    require([queue.digest(p) for p in sources] == hashes, 'input changed during simulation')
    stage = Path(tempfile.mkdtemp(prefix='.plo-math-', dir=parent))
    try:
        (stage / 'hands').mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        (stage / 'manifest.json').write_bytes(json_bytes(manifest))
        require([queue.digest(p) for p in sources] == hashes, 'input changed before publishing')
        require(not destination.exists() and not destination.is_symlink(),
                'output appeared during processing')
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest



def verify_results(plan_path, annotations_path, queue_path, directory):
    """Check exported results without rerunning Monte Carlo (not a math audit)."""
    verified, hashes = verify_inputs(plan_path, annotations_path, queue_path)
    root = Path(directory)
    require(root.is_dir() and not root.is_symlink(), 'invalid results directory')
    manifest_path = root / 'manifest.json'
    manifest = queue.read(manifest_path)
    require(manifest.get('schema_version') == 1 and
            manifest.get('status') == 'offline_reviewed_conditional_monte_carlo_results' and
            manifest.get('source_plan_sha256') == hashes[0] and
            manifest.get('source_annotations_sha256') == hashes[1] and
            manifest.get('source_queue_sha256') == hashes[2] and
            manifest.get('source_video_sha256_claim') == verified['source_video_sha256_claim'] and
            manifest.get('video_or_ocr_verified') is False and
            manifest.get('actions_observed_or_graded') is False and
            manifest.get('ci95_is_sampling_error_only') is True,
            'invalid result manifest provenance')
    rows = manifest.get('hands')
    require(type(rows) is list and len(rows) == len(verified['entries']),
            'invalid result hand count')
    require((root / 'hands').is_dir() and not (root / 'hands').is_symlink(),
            'invalid hands directory')
    expected_files = {'manifest.json'}
    total = analyzed = blocked = 0
    for original, row in zip(verified['entries'], rows):
        require(type(row) is dict and
                all(row.get(k) == original[k] for k in
                    ('hand_id', 'table_id', 'start_seconds', 'end_seconds')) and
                row.get('reviewer_confidence_declared_not_calibrated') ==
                    original['reviewer_confidence_declared_not_calibrated'],
                'result hand identity mismatch')
        if not original['eligible_for_offline_monte_carlo']:
            blocked += 1
            require(row.get('status') == 'blocked_not_analyzed' and
                    row.get('blocked_reasons') == original['blocked_reasons'] and
                    row.get('result_file') is None and row.get('result_sha256') is None,
                    'blocked hand unexpectedly analyzed')
            continue
        analyzed += 1
        data = original['equity_input']
        name = 'hands/' + original['hand_id'] + '.json'
        require(row.get('status') == 'offline_conditional_equity_computed' and
                row.get('result_file') == name and
                row.get('equity_input_sha256') == sha_bytes(json_bytes(data)),
                'result input binding mismatch')
        path = root / name
        require(path.is_file() and not path.is_symlink() and
                queue.digest(path) == row.get('result_sha256'),
                'result file digest mismatch')
        result = queue.read(path)
        wins, ties, losses = [result.get(k) for k in
                               ('win_count', 'tie_count', 'loss_count')]
        n = data['iterations']
        require(all(type(x) is int and 0 <= x <= n for x in (wins, ties, losses)) and
                wins + ties + losses == n and
                result.get('iterations') == n and result.get('seed') == data['seed'] and
                result.get('variant') == data['variant'] and
                result.get('hero_cards') == data['hero_cards'] and
                result.get('board_cards') == data['board_cards'] and
                result.get('opponent_model_kind') == data['opponent_model']['kind'] and
                result.get('analysis_status') == 'offline_manual_assumptions_monte_carlo_only' and
                result.get('ocr_semantics_verified') is False and
                result.get('strategic_correctness_verified') is False,
                'invalid result semantics')
        estimated = (wins + ties/2)/n
        require(result.get('equity') == estimated and
                row.get('equity') == estimated and
                row.get('equity_ci95_sampling_only') == result.get('equity_ci95_sampling_only') and
                row.get('seed') == data['seed'] and row.get('iterations') == n,
                'invalid equity statistics')
        require(row.get('terminal_call_ev_model') == result.get('terminal_call_ev_model') and
                (('terminal_call_ev_model' in result) == ('pot_now' in data)),
                'invalid conditional EV binding')
        total += n
        expected_files.add(name)
    actual_files = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink in results')
        if path.is_file():
            actual_files.add(path.relative_to(root).as_posix())
    require(actual_files == expected_files, 'unexpected or missing result files')
    require(manifest.get('eligible_analyzed_count') == analyzed and
            manifest.get('blocked_count') == blocked and
            manifest.get('total_iterations') == total,
            'manifest totals mismatch')
    return {'verified': analyzed, 'blocked': blocked, 'iterations': total}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='verify existing output without rerunning Monte Carlo')
    parser.add_argument('reviewed_plan_json')
    parser.add_argument('manual_cards_json')
    parser.add_argument('verified_queue_json')
    parser.add_argument('new_output_directory')
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_results(args.reviewed_plan_json, args.manual_cards_json,
                                        args.verified_queue_json, args.new_output_directory)))
    else:
        manifest = run(args.reviewed_plan_json, args.manual_cards_json,
                       args.verified_queue_json, args.new_output_directory)
        print(json.dumps({'analyzed': manifest['eligible_analyzed_count'],
                          'blocked': manifest['blocked_count'],
                          'iterations': manifest['total_iterations']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
