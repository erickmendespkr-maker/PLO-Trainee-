"""Offline, bounded, resumable execution and verified cross-batch hand history.

Usage: python offline_session_batch_history.py PLAN ANNOTATIONS BATCH_DIR RESULTS_DIR [--max-new N]
       python offline_session_batch_history.py --verify PLAN ANNOTATIONS BATCH_DIR RESULTS_DIR

Only human-reviewed, previously prepared batches; no video OCR, real-time poker,
or automatic decision grading. Results are conditional on unverified ranges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import offline_session_batch_planner as planner
import offline_reviewed_math_runner as runner
import offline_reviewed_hand_math_queue as queue

HISTORY_NAME = 'session_history.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def safe_file(path):
    require(path.is_file() and not path.is_symlink(), 'missing or symlinked file: ' + str(path))
    return path.read_bytes()


def inputs(plan_path, annotations_path, batches_root):
    plan_path, annotations_path, batches_root = map(Path, (plan_path, annotations_path, batches_root))
    planner.process(plan_path, annotations_path, batches_root, verify=True)
    raw = safe_file(batches_root/'manifest.json')
    manifest = queue.read(batches_root/'manifest.json')
    require(type(manifest) is dict and manifest.get('monte_carlo_executed') is False,
            'batch plan cannot claim executed calculations')
    return manifest, sha(raw)


def scan(plan_manifest, batch_sha, batches_root, results_root):
    """Verify each completed result against original inputs; require a prefix."""
    batches_root, results_root = Path(batches_root), Path(results_root)
    rows = plan_manifest['batches']
    require(results_root.is_dir() and not results_root.is_symlink(), 'invalid results directory')
    allowed = {r['directory'] for r in rows} | {HISTORY_NAME}
    require(all(p.name in allowed and not p.is_symlink() for p in results_root.iterdir()),
            'unexpected entry or symlink in results directory')
    completed = []
    all_hands = []
    missing_started = False
    for item in rows:
        name = item['directory']
        folder = results_root/name
        if not folder.exists():
            require(not folder.is_symlink(), 'symlinked result directory')
            missing_started = True
            continue
        require(not missing_started, 'non-prefix result batch')
        require(folder.is_dir() and not folder.is_symlink(), 'invalid result batch directory')
        source = batches_root/name
        checked = runner.verify_results(source/'plan.json', source/'annotations.json',
                                        source/'queue.json', folder)
        require(checked['verified'] == item['eligible'] and
                checked['blocked'] == item['blocked'] and
                checked['iterations'] == item['iterations'],
                'result totals differ from batch budget')
        manifest_bytes = safe_file(folder/'manifest.json')
        math_manifest = queue.read(folder/'manifest.json')
        completed.append({'directory': name, 'math_manifest_sha256': sha(manifest_bytes),
                          'analyzed': checked['verified'], 'blocked': checked['blocked'],
                          'iterations': checked['iterations']})
        for hand in math_manifest['hands']:
            entry = {'batch': name, 'hand_id': hand['hand_id'],
                     'table_id': hand['table_id'], 'start_seconds': hand['start_seconds'],
                     'end_seconds': hand['end_seconds'], 'status': hand['status'],
                     'reviewer_confidence_declared_not_calibrated':
                         hand['reviewer_confidence_declared_not_calibrated']}
            if hand['status'] == 'offline_conditional_equity_computed':
                entry.update(equity=hand['equity'],
                             equity_ci95_sampling_only=hand['equity_ci95_sampling_only'],
                             terminal_call_ev_model=hand['terminal_call_ev_model'],
                             iterations=hand['iterations'], seed=hand['seed'],
                             result_sha256=hand['result_sha256'],
                             result_path=name + '/' + hand['result_file'])
            else:
                entry['blocked_reasons'] = hand['blocked_reasons']
            all_hands.append(entry)
    require(len({x['hand_id'] for x in all_hands}) == len(all_hands),
            'duplicate hand across batches')
    all_hands.sort(key=lambda x: (x['start_seconds'], x['table_id'], x['hand_id']))
    return {'schema_version': 1, 'status': 'offline_conditional_batch_history',
            'source_batch_manifest_sha256': batch_sha,
            'source_plan_sha256': plan_manifest['source_plan_sha256'],
            'source_annotations_sha256': plan_manifest['source_annotations_sha256'],
            'source_video_sha256_claim': plan_manifest['source_video_sha256_claim'],
            'total_batches': len(rows), 'completed_batches': len(completed),
            'complete': len(completed) == len(rows),
            'total_hands_reviewed': len(all_hands),
            'eligible_analyzed': sum(x['analyzed'] for x in completed),
            'blocked': sum(x['blocked'] for x in completed),
            'total_iterations': sum(x['iterations'] for x in completed),
            'ocr_verified': False, 'human_card_claims_independently_verified': False,
            'ranges_are_hypotheses': True, 'ci95_is_sampling_error_only': True,
            'actions_observed_or_graded': False,
            'terminal_call_ev_is_conditional_not_realized': True,
            'batches': completed, 'hands': all_hands}


def verify_history(previous, current):
    """Accept only exact existing history for a verified completed prefix.

    A prefix may be shorter than current after a crash between an atomic batch
    publication and history update; all content still must match exactly.
    """
    n = previous.get('completed_batches') if type(previous) is dict else None
    require(type(n) is int and 0 <= n <= current['completed_batches'],
            'invalid previous history length')
    prior_batches = previous.get('batches')
    require(type(prior_batches) is list and prior_batches == current['batches'][:n],
            'previous history batch mismatch')
    # Regenerate expected history from the already-verified prefix, preserving
    # only those hands whose batch is in that prefix.
    allowed = {b['directory'] for b in current['batches'][:n]}
    expected = dict(current)
    expected['batches'] = current['batches'][:n]
    expected['hands'] = [h for h in current['hands'] if h['batch'] in allowed]
    expected['completed_batches'] = n
    expected['complete'] = n == current['total_batches']
    expected['total_hands_reviewed'] = len(expected['hands'])
    expected['eligible_analyzed'] = sum(b['analyzed'] for b in expected['batches'])
    expected['blocked'] = sum(b['blocked'] for b in expected['batches'])
    expected['total_iterations'] = sum(b['iterations'] for b in expected['batches'])
    require(previous == expected, 'previous history differs from verified results')


def atomic_history(root, history):
    fd, tmp = tempfile.mkstemp(prefix='.plo-history-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(encode(history))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, root/HISTORY_NAME)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def process(plan_path, annotations_path, batches_root, results_root, *, verify=False, max_new=1):
    require(type(max_new) is int and 0 <= max_new <= 100,
            'max-new must be an integer between 0 and 100')
    plan_manifest, batch_sha = inputs(plan_path, annotations_path, batches_root)
    results_root = Path(results_root)
    require(results_root.parent.is_dir() and not results_root.parent.is_symlink() and
            not results_root.is_symlink() and
            results_root.resolve() != Path(batches_root).resolve(),
            'invalid output location')
    if not results_root.exists():
        require(not verify, 'results directory does not exist')
        results_root.mkdir()
    current = scan(plan_manifest, batch_sha, batches_root, results_root)
    previous_path = results_root/HISTORY_NAME
    if previous_path.exists() or previous_path.is_symlink():
        previous = queue.read(previous_path) if not previous_path.is_symlink() else None
        verify_history(previous, current)
    if verify:
        require(previous_path.is_file() and not previous_path.is_symlink() and
                safe_file(previous_path) == encode(current), 'history not current or altered')
        return current
    done = current['completed_batches']
    for item in plan_manifest['batches'][done:done + max_new]:
        folder = Path(batches_root)/item['directory']
        runner.run(folder/'plan.json', folder/'annotations.json', folder/'queue.json',
                   results_root/item['directory'])
        current = scan(plan_manifest, batch_sha, batches_root, results_root)
        atomic_history(results_root, current)
    if not previous_path.exists() or safe_file(previous_path) != encode(current):
        atomic_history(results_root, current)
    return current


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify', action='store_true')
    p.add_argument('--max-new', type=int, default=1)
    p.add_argument('plan'); p.add_argument('annotations')
    p.add_argument('batches'); p.add_argument('results')
    a = p.parse_args(argv)
    result = process(a.plan, a.annotations, a.batches, a.results,
                     verify=a.verify, max_new=a.max_new)
    print(json.dumps({k: result[k] for k in ('completed_batches', 'total_batches',
          'eligible_analyzed', 'blocked', 'total_iterations', 'complete')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
