"""Run bounded offline PLO5/PLO6 Monte Carlo on a human-reviewed queue.

Usage: python offline_reviewed_math_batch.py QUEUE.json NEW_RESULTS_DIRECTORY

All cards, video timestamps, player identities and opponent ranges remain HUMAN
ASSERTIONS. The 95% confidence interval covers simulation sampling error only.
No OCR, real-time poker interaction, betting, or strategic grading occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

import offline_plo_equity_monte_carlo as monte_carlo
import offline_reviewed_hand_math_queue as queue_module

ID = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_HANDS = 100
MAX_ITERATIONS_PER_HAND = 5000
MAX_ITERATIONS_PER_BATCH = 20000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def encode_json(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def validate_queue(queue):
    """Reject unsupported or internally inconsistent queues before doing any work."""
    require(type(queue) is dict and queue.get('schema_version') == 1 and
            queue.get('status') == 'offline_human_reviewed_math_inputs_not_executed' and
            queue.get('equity_or_ev_calculated') is False and
            queue.get('ocr_semantics_verified') is False and
            queue.get('video_card_visibility_machine_verified') is False and
            queue.get('reviewed_cards_are_human_assertions') is True and
            queue.get('opponent_ranges_are_assumptions') is True and
            queue.get('reviewer_confidence_is_not_statistical_confidence') is True and
            queue.get('action_observed_or_graded') is False,
            'unsupported queue provenance or claims')
    require(set(queue) == {'schema_version', 'status', 'source_video_sha256_claim',
                           'source_plan_sha256', 'source_annotations_sha256', 'entries',
                           'eligible_count', 'blocked_count', 'equity_or_ev_calculated',
                           'ocr_semantics_verified', 'video_card_visibility_machine_verified',
                           'reviewed_cards_are_human_assertions',
                           'opponent_ranges_are_assumptions',
                           'reviewer_confidence_is_not_statistical_confidence',
                           'action_observed_or_graded', 'warning'},
            'unexpected queue fields')
    for key in ('source_video_sha256_claim', 'source_plan_sha256',
                'source_annotations_sha256'):
        require(type(queue.get(key)) is str and SHA.fullmatch(queue[key]),
                f'invalid {key}')
    entries = queue.get('entries')
    require(type(entries) is list and 1 <= len(entries) <= MAX_HANDS,
            'queue must contain 1..100 entries')
    ids, tables, eligible, blocked, iterations = set(), set(), 0, 0, 0
    for row in entries:
        require(type(row) is dict and set(row) == {
            'hand_id', 'table_id', 'start_seconds', 'end_seconds',
            'eligible_for_offline_monte_carlo', 'equity_input', 'blocked_reasons',
            'reviewer_confidence_declared_not_calibrated'}, 'invalid queue entry fields')
        hand, table = row['hand_id'], row['table_id']
        require(type(hand) is str and ID.fullmatch(hand) and hand not in ids and
                type(table) is str and ID.fullmatch(table), 'invalid/duplicate hand or table ID')
        ids.add(hand)
        tables.add(table)
        start, end = row['start_seconds'], row['end_seconds']
        require(queue_module.number(start, 0, 14400) and
                queue_module.number(end, 0, 14400) and .1 <= end-start <= 300,
                'invalid clip timestamps')
        confidence = row['reviewer_confidence_declared_not_calibrated']
        require(confidence is None or queue_module.number(confidence, 0, 1),
                'invalid reviewer confidence')
        flag, inp, reasons = (row['eligible_for_offline_monte_carlo'],
                              row['equity_input'], row['blocked_reasons'])
        require(type(flag) is bool and type(reasons) is list and
                all(type(r) is str and 1 <= len(r) <= 100 for r in reasons),
                'invalid queue eligibility or reasons')
        if flag:
            require(type(inp) is dict and not reasons and
                    inp.get('manual_review_confirmed') is True,
                    'eligible hand must have reviewed input without blockers')
            n = inp.get('iterations')
            require(type(n) is int and 2 <= n <= MAX_ITERATIONS_PER_HAND,
                    'per-hand iteration safety limit exceeded')
            iterations += n
            eligible += 1
        else:
            require(inp is None and reasons, 'blocked hand must have reasons and no input')
            blocked += 1
    require(len(tables) <= 4, 'more than four tables')
    require(type(queue.get('eligible_count')) is int and
            type(queue.get('blocked_count')) is int and
            queue['eligible_count'] == eligible and queue['blocked_count'] == blocked,
            'queue eligibility counts mismatch')
    require(eligible >= 1, 'no eligible hands to analyze')
    require(iterations <= MAX_ITERATIONS_PER_BATCH,
            'batch iteration safety limit exceeded')
    return entries, iterations


def analyze_batch(queue, queue_hash, engine_hash):
    entries, total_iterations = validate_queue(queue)
    results, records = {}, []
    for row in entries:
        hand = row['hand_id']
        if not row['eligible_for_offline_monte_carlo']:
            records.append({'hand_id': hand, 'table_id': row['table_id'],
                            'status': 'blocked_not_analyzed',
                            'blocked_reasons': row['blocked_reasons'],
                            'result_file': None, 'result_sha256': None})
            continue
        analysis = monte_carlo.analyze(row['equity_input'])
        require(analysis.get('analysis_status') ==
                'offline_manual_assumptions_monte_carlo_only' and
                analysis.get('strategic_correctness_verified') is False and
                analysis.get('ocr_semantics_verified') is False and
                analysis.get('exactly_two_hole_three_board_rule') is True and
                analysis.get('iterations') == row['equity_input']['iterations'] and
                analysis.get('seed') == row['equity_input']['seed'] and
                analysis.get('variant') == row['equity_input']['variant'] and
                analysis.get('hero_cards') == row['equity_input']['hero_cards'] and
                analysis.get('board_cards') == row['equity_input']['board_cards'],
                'engine returned unsupported or mismatched analysis')
        result = {
            'schema_version': 1,
            'status': 'offline_reviewed_queue_monte_carlo_sampling_only',
            'hand_id': hand, 'table_id': row['table_id'],
            'start_seconds': row['start_seconds'],
            'end_seconds': row['end_seconds'],
            'source_queue_sha256': queue_hash,
            'engine_sha256': engine_hash,
            'source_video_sha256_claim_not_independently_verified': queue['source_video_sha256_claim'],
            'source_plan_sha256_claim': queue['source_plan_sha256'],
            'source_annotations_sha256_claim': queue['source_annotations_sha256'],
            'reviewer_confidence_declared_not_calibrated': row['reviewer_confidence_declared_not_calibrated'],
            'opponent_ranges_are_assumptions': True,
            'equity_ci95_covers_sampling_only': True,
            'action_observed_or_graded': False,
            'visual_evidence_machine_verified': False,
            'equity_result': analysis,
        }
        filename = f'{hand}.equity.json'
        raw = encode_json(result)
        results[filename] = raw
        records.append({'hand_id': hand, 'table_id': row['table_id'],
                        'status': 'monte_carlo_executed_under_manual_assumptions',
                        'blocked_reasons': [], 'result_file': filename,
                        'result_sha256': hashlib.sha256(raw).hexdigest()})
    manifest = {'schema_version': 1,
                'status': 'offline_reviewed_math_batch_monte_carlo_sampling_only',
                'source_queue_sha256': queue_hash,
                'engine_sha256': engine_hash,
                'source_video_sha256_claim_not_independently_verified': queue['source_video_sha256_claim'],
                'total_iterations': total_iterations,
                'eligible_executed': len(results),
                'blocked_not_executed': len(entries) - len(results),
                'entries': records,
                'opponent_ranges_are_assumptions': True,
                'equity_ci95_covers_sampling_only': True,
                'action_observed_or_graded': False,
                'visual_evidence_machine_verified': False,
                'warning': 'Monte Carlo estimates conditional on human-declared cards/ranges. Sampling intervals do not cover visual, identity, range or action uncertainty.'}
    return results, manifest


def run(queue_path, destination):
    source, dest = Path(queue_path), Path(destination)
    require(source.is_file() and not source.is_symlink() and
            dest.name not in ('', '.', '..') and dest.parent.is_dir() and
            not dest.parent.is_symlink() and not dest.exists() and
            not dest.is_symlink() and dest.resolve() != source.resolve(),
            'destination must be a new directory; input must be a regular file')
    engine_path = Path(monte_carlo.__file__)
    require(engine_path.is_file() and not engine_path.is_symlink(), 'unsafe engine source')
    queue_hash, engine_hash = sha256(source), sha256(engine_path)
    queue = queue_module.read(source)
    files, manifest = analyze_batch(queue, queue_hash, engine_hash)
    require(sha256(source) == queue_hash and sha256(engine_path) == engine_hash,
            'input or engine changed during analysis')
    # Compute and validate everything before creating the output directory.
    files['manifest.json'] = encode_json(manifest)
    dest.mkdir(exist_ok=False)
    try:
        for name, raw in files.items():
            (dest / name).write_bytes(raw)
    except BaseException:
        shutil.rmtree(dest)
        raise
    return manifest


def verify_results(directory, source_queue=None):
    root = Path(directory)
    require(root.is_dir() and not root.is_symlink(), 'invalid results directory')
    manifest_path = root / 'manifest.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'missing manifest')
    manifest = queue_module.read(manifest_path)
    require(manifest.get('schema_version') == 1 and
            manifest.get('status') == 'offline_reviewed_math_batch_monte_carlo_sampling_only' and
            manifest.get('opponent_ranges_are_assumptions') is True and
            manifest.get('equity_ci95_covers_sampling_only') is True and
            manifest.get('action_observed_or_graded') is False and
            manifest.get('visual_evidence_machine_verified') is False and
            type(manifest.get('entries')) is list and
            1 <= len(manifest['entries']) <= MAX_HANDS,
            'unsupported result manifest')
    require(type(manifest.get('source_queue_sha256')) is str and
            SHA.fullmatch(manifest['source_queue_sha256']) and
            type(manifest.get('engine_sha256')) is str and
            SHA.fullmatch(manifest['engine_sha256']), 'invalid manifest hashes')
    if source_queue is not None:
        p = Path(source_queue)
        require(p.is_file() and not p.is_symlink() and
                sha256(p) == manifest['source_queue_sha256'],
                'source queue digest mismatch')
    expected, seen, executed, blocked, total_iterations = {'manifest.json'}, set(), 0, 0, 0
    for row in manifest['entries']:
        require(type(row) is dict and set(row) == {'hand_id', 'table_id', 'status',
                'blocked_reasons', 'result_file', 'result_sha256'}, 'invalid result row')
        hand, table = row['hand_id'], row['table_id']
        require(type(hand) is str and ID.fullmatch(hand) and hand not in seen and
                type(table) is str and ID.fullmatch(table), 'invalid result identity')
        seen.add(hand)
        if row['status'] == 'blocked_not_analyzed':
            require(row['result_file'] is None and row['result_sha256'] is None and
                    type(row['blocked_reasons']) is list and row['blocked_reasons'],
                    'invalid blocked record')
            blocked += 1
            continue
        require(row['status'] == 'monte_carlo_executed_under_manual_assumptions' and
                row['blocked_reasons'] == [] and
                row['result_file'] == f'{hand}.equity.json' and
                type(row['result_sha256']) is str and SHA.fullmatch(row['result_sha256']),
                'invalid executed record')
        filename = row['result_file']
        expected.add(filename)
        path = root / filename
        require(path.is_file() and not path.is_symlink() and
                sha256(path) == row['result_sha256'], 'result digest mismatch')
        data = queue_module.read(path)
        result = data.get('equity_result')
        require(data.get('status') == 'offline_reviewed_queue_monte_carlo_sampling_only' and
                data.get('hand_id') == hand and data.get('table_id') == table and
                data.get('source_queue_sha256') == manifest['source_queue_sha256'] and
                data.get('engine_sha256') == manifest['engine_sha256'] and
                data.get('opponent_ranges_are_assumptions') is True and
                data.get('equity_ci95_covers_sampling_only') is True and
                data.get('action_observed_or_graded') is False and
                data.get('visual_evidence_machine_verified') is False and
                type(result) is dict and
                result.get('analysis_status') == 'offline_manual_assumptions_monte_carlo_only' and
                result.get('strategic_correctness_verified') is False and
                result.get('ocr_semantics_verified') is False and
                result.get('exactly_two_hole_three_board_rule') is True and
                type(result.get('iterations')) is int and
                2 <= result['iterations'] <= MAX_ITERATIONS_PER_HAND,
                'unsupported analysis record')
        total_iterations += result['iterations']
        executed += 1
    require({p.name for p in root.iterdir()} == expected and
            manifest.get('eligible_executed') == executed and
            manifest.get('blocked_not_executed') == blocked and
            manifest.get('total_iterations') == total_iterations and
            total_iterations <= MAX_ITERATIONS_PER_BATCH,
            'result file set or counts mismatch')
    return {'verified': executed, 'blocked': blocked, 'total_iterations': total_iterations,
            'source_queue_sha256': manifest['source_queue_sha256']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true',
                        help='verify existing results directory; second argument is optional source queue')
    parser.add_argument('first')
    parser.add_argument('second', nargs='?')
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_results(args.first, args.second)))
    else:
        require(args.second is not None, 'new results directory required')
        manifest = run(args.first, args.second)
        print(json.dumps({'executed': manifest['eligible_executed'],
                          'blocked': manifest['blocked_not_executed'],
                          'iterations': manifest['total_iterations'],
                          'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
