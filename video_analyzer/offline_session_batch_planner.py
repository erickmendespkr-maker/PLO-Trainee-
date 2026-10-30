"""Split a long HUMAN-REVIEWED offline PLO session into bounded math batches.

Usage: python offline_session_batch_planner.py PLAN ANNOTATIONS NEW_DIR
       python offline_session_batch_planner.py --verify PLAN ANNOTATIONS DIR

No OCR, video capture, Monte Carlo, poker-site access or action grading. Every
batch is compatible with offline_reviewed_math_runner; this command NEVER runs it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import offline_reviewed_hand_math_queue as q
import offline_reviewed_math_runner as runner

MAX_SOURCE_CLIPS = 4000
MAX_BATCH_CLIPS = 100
MAX_BATCH_ELIGIBLE = runner.MAX_ELIGIBLE_HANDS
MAX_BATCH_ITERATIONS = runner.MAX_TOTAL_ITERATIONS


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_sources(plan_path, annotations_path):
    paths = [Path(plan_path), Path(annotations_path)]
    require(paths[0].resolve() != paths[1].resolve(), 'source files must be distinct')
    hashes = [q.digest(p) for p in paths]
    plan, annotations = [q.read(p) for p in paths]
    require(type(plan) is dict and set(plan) ==
            {'schema_version', 'status', 'source_video_sha256', 'equity_or_ev_calculated', 'clips'} and
            plan['schema_version'] == 1 and
            plan['status'] == 'human_reviewed_clip_plan_not_automated_hand_detection' and
            plan['equity_or_ev_calculated'] is False and
            type(plan['source_video_sha256']) is str and
            q.SHA.fullmatch(plan['source_video_sha256']) and
            type(plan['clips']) is list and 1 <= len(plan['clips']) <= MAX_SOURCE_CLIPS,
            'invalid long-session reviewed plan')
    require(type(annotations) is dict and set(annotations) ==
            {'schema_version', 'source_plan_sha256', 'hands'} and
            annotations['schema_version'] == 1 and
            annotations['source_plan_sha256'] == hashes[0] and
            type(annotations['hands']) is list and len(annotations['hands']) <= len(plan['clips']),
            'invalid or unbound long-session annotations')
    by_hand, tables = {}, {}
    for clip in plan['clips']:
        # Reuse the actual existing schema validator without its 100-clip ceiling.
        q.validate_plan({**plan, 'clips': [clip]})
        hand, table = clip['hand_id'], clip['table_id']
        require(hand not in by_hand, 'duplicate hand ID across session')
        require(clip['end_seconds'] <= 3600, 'session exceeds 60 minutes')
        by_hand[hand] = clip
        tables.setdefault(table, []).append(clip)
    require(len(tables) <= 4, 'more than four tables')
    for group in tables.values():
        ordered = sorted(group, key=lambda c: (c['start_seconds'], c['end_seconds']))
        require(all(b['start_seconds'] >= a['end_seconds'] for a, b in zip(ordered, ordered[1:])),
                'overlapping hands on one table')
    seen = set()
    for item in annotations['hands']:
        require(type(item) is dict and type(item.get('hand_id')) is str and
                item['hand_id'] in by_hand and item['hand_id'] not in seen and
                item.get('table_id') == by_hand[item['hand_id']]['table_id'],
                'unknown, duplicate or cross-table annotation')
        seen.add(item['hand_id'])
    require([q.digest(p) for p in paths] == hashes, 'source changed during validation')
    return plan, annotations, hashes


def plan_batches(plan, annotations):
    annotations_by_id = {h['hand_id']: h for h in annotations['hands']}
    ordered = sorted(plan['clips'], key=lambda c: (c['start_seconds'], c['table_id'], c['hand_id']))
    groups, current = [], []
    eligible = iterations = 0
    for clip in ordered:
        item = annotations_by_id.get(clip['hand_id'])
        one_plan = {**plan, 'clips': [clip]}
        # A single-entry queue gives the authoritative eligibility and rejects bad annotations.
        one_ann = {'schema_version': 1, 'source_plan_sha256': 'a'*64,
                   'hands': [item] if item is not None else []}
        entry = q.build(one_plan, one_ann, 'a'*64, 'b'*64)['entries'][0]
        count = int(entry['eligible_for_offline_monte_carlo'])
        cost = entry['equity_input']['iterations'] if count else 0
        if current and (len(current) >= MAX_BATCH_CLIPS or
                        eligible + count > MAX_BATCH_ELIGIBLE or
                        iterations + cost > MAX_BATCH_ITERATIONS):
            groups.append(current)
            current, eligible, iterations = [], 0, 0
        current.append(clip)
        eligible += count
        iterations += cost
    if current:
        groups.append(current)
    output = []
    for clips in groups:
        batch_plan = {**plan, 'clips': clips}
        p_raw = encode(batch_plan)
        batch_ann = {'schema_version': 1, 'source_plan_sha256': digest(p_raw),
                     'hands': [annotations_by_id[c['hand_id']] for c in clips
                               if c['hand_id'] in annotations_by_id]}
        a_raw = encode(batch_ann)
        queue = q.build(batch_plan, batch_ann, digest(p_raw), digest(a_raw))
        require(queue['eligible_count'] <= MAX_BATCH_ELIGIBLE and
                sum(e['equity_input']['iterations'] for e in queue['entries']
                    if e['eligible_for_offline_monte_carlo']) <= MAX_BATCH_ITERATIONS,
                'batch simulation budget exceeded')
        output.append((p_raw, a_raw, encode(queue), queue))
    return output


def manifest_for(batches, source_hashes, plan):
    rows = []
    for i, (p, a, queue_raw, data) in enumerate(batches, 1):
        rows.append({'directory': f'batch-{i:04d}', 'plan_sha256': digest(p),
                     'annotations_sha256': digest(a), 'queue_sha256': digest(queue_raw),
                     'clips': len(data['entries']), 'eligible': data['eligible_count'],
                     'blocked': data['blocked_count'],
                     'iterations': sum(e['equity_input']['iterations'] for e in data['entries']
                                       if e['eligible_for_offline_monte_carlo'])})
    return {'schema_version': 1, 'status': 'offline_human_reviewed_math_batches_not_executed',
            'source_plan_sha256': source_hashes[0],
            'source_annotations_sha256': source_hashes[1],
            'source_video_sha256_claim': plan['source_video_sha256'],
            'total_clips': len(plan['clips']), 'total_batches': len(rows),
            'monte_carlo_executed': False, 'ocr_verified': False,
            'action_graded': False, 'ranges_are_hypotheses': True, 'batches': rows}


def process(plan_path, annotations_path, destination, verify=False):
    plan, ann, hashes = checked_sources(plan_path, annotations_path)
    batches = plan_batches(plan, ann)
    manifest = manifest_for(batches, hashes, plan)
    root = Path(destination)
    require(root.parent.is_dir() and not root.parent.is_symlink() and
            not root.is_symlink(), 'invalid destination parent or symlink')
    if verify:
        require(root.is_dir() and not root.is_symlink(), 'missing batch directory')
        expected_dirs = {row['directory'] for row in manifest['batches']}
        require({p.name for p in root.iterdir()} == expected_dirs | {'manifest.json'},
                'unexpected or missing batch files')
        require((root / 'manifest.json').is_file() and
                not (root / 'manifest.json').is_symlink() and
                (root / 'manifest.json').read_bytes() == encode(manifest),
                'batch manifest differs')
        for row, (p, a, queue_raw, _) in zip(manifest['batches'], batches):
            folder = root / row['directory']
            require(folder.is_dir() and not folder.is_symlink() and
                    {x.name for x in folder.iterdir()} == {'plan.json', 'annotations.json', 'queue.json'},
                    'invalid batch directory')
            for name, raw in [('plan.json', p), ('annotations.json', a), ('queue.json', queue_raw)]:
                f = folder / name
                require(f.is_file() and not f.is_symlink() and f.read_bytes() == raw,
                        'batch input differs: ' + name)
            runner.verify_inputs(folder/'plan.json', folder/'annotations.json', folder/'queue.json')
    else:
        require(not root.exists(), 'output already exists')
        stage = Path(tempfile.mkdtemp(prefix='.plo-batches-', dir=root.parent))
        try:
            for row, (p, a, queue_raw, _) in zip(manifest['batches'], batches):
                folder = stage / row['directory']
                folder.mkdir()
                for name, raw in [('plan.json', p), ('annotations.json', a), ('queue.json', queue_raw)]:
                    (folder / name).write_bytes(raw)
                runner.verify_inputs(folder/'plan.json', folder/'annotations.json', folder/'queue.json')
            (stage/'manifest.json').write_bytes(encode(manifest))
            require([q.digest(Path(plan_path)), q.digest(Path(annotations_path))] == hashes,
                    'source changed before publication')
            require(not root.exists() and not root.is_symlink(), 'output appeared during processing')
            os.rename(stage, root)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {'batches': len(batches), 'clips': len(plan['clips']),
            'eligible': sum(row['eligible'] for row in manifest['batches']),
            'blocked': sum(row['blocked'] for row in manifest['batches']),
            'verified': verify, 'monte_carlo_executed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('plan'); parser.add_argument('annotations'); parser.add_argument('directory')
    args = parser.parse_args(argv)
    print(json.dumps(process(args.plan, args.annotations, args.directory, args.verify)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
