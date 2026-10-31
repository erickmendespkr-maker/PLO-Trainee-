"""Offline selection and batch export of conditional PLO5/PLO6 EV clips.

Usage: python offline_ev_batch_clips.py SUMMARY.json VIDEO.mp4 BATCH.json EMPTY_OUT_DIR

BATCH.json contains {"schema_version":1,"status":"manual_offline_decision_batch_unverified",
"max_clips":1..20,"min_gap_chips":nonnegative,"entries":[{"ev_json":"EV.json",
"decision_json":"DECISION.json","clip_id":"safe-id"}, ...]}. Entry paths
must be regular files directly beside BATCH.json. No real-time poker access.

All decisions, action timestamps, ranges and reviewer confidence are unverified.
Ranking uses only *conditional model differences*, not a poker-error verdict.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

import offline_ev_decision_clip as single
import offline_mc_input_contract as contract

MAX_ENTRIES = 40
MAX_CLIPS = 20
MAX_JSON_BYTES = 5_000_000


def require(ok, why):
    contract.check(ok, why)


def regular(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON_BYTES,
            'missing, symlinked or oversized JSON input')
    return path


def entry_path(base, name):
    require(type(name) is str and name not in ('', '.', '..') and
            Path(name).name == name and '/' not in name and '\\' not in name and
            name.endswith('.json'), 'entry JSON must be a basename in batch directory')
    return regular(base / name)


def prepare(summary_path, video_path, batch_path, out_dir):
    """Preflight *all* entries before rendering any MP4."""
    summary_path, video_path, batch_path, out_dir = map(Path, (summary_path, video_path, batch_path, out_dir))
    require(out_dir.is_dir() and not out_dir.is_symlink(), 'output directory must exist')
    require(not (out_dir / 'batch_report.json').exists() and
            not (out_dir / 'batch_report.json').is_symlink(), 'batch report already exists')
    require(len({p.resolve() for p in (summary_path, video_path, batch_path, out_dir)}) == 4,
            'distinct inputs and output directory required')
    regular(summary_path)
    regular(batch_path)
    duration = single.video_duration(video_path)
    inputs = {str(p.resolve()): (p, contract.sha256(p)) for p in (summary_path, video_path, batch_path)}
    summary_sha = inputs[str(summary_path.resolve())][1]
    video_sha = inputs[str(video_path.resolve())][1]
    summary = contract.read_json(summary_path)
    batch = contract.read_json(batch_path)
    require(type(batch) is dict and set(batch) == {
        'schema_version', 'status', 'max_clips', 'min_gap_chips', 'entries'}, 'invalid batch schema')
    require(type(batch['schema_version']) is int and batch['schema_version'] == 1 and
            batch['status'] == 'manual_offline_decision_batch_unverified' and
            type(batch['max_clips']) is int and 1 <= batch['max_clips'] <= MAX_CLIPS and
            type(batch['min_gap_chips']) in (int, float) and
            math.isfinite(batch['min_gap_chips']) and 0 <= batch['min_gap_chips'] <= 1e9 and
            type(batch['entries']) is list and 1 <= len(batch['entries']) <= MAX_ENTRIES,
            'invalid batch parameters')
    plans = []
    ids, decision_keys, pairs, tables = set(), set(), set(), set()
    for item in batch['entries']:
        require(type(item) is dict and set(item) == {'ev_json', 'decision_json', 'clip_id'},
                'invalid batch entry')
        clip_id = item['clip_id']
        require(type(clip_id) is str and contract.ID.fullmatch(clip_id) and
                clip_id != 'batch_report' and clip_id not in ids, 'duplicate or unsafe clip ID')
        ids.add(clip_id)
        ev_path = entry_path(batch_path.parent, item['ev_json'])
        decision_path = entry_path(batch_path.parent, item['decision_json'])
        require(ev_path.resolve() != decision_path.resolve() and
                ev_path.resolve() not in (summary_path.resolve(), video_path.resolve(), batch_path.resolve()) and
                decision_path.resolve() not in (summary_path.resolve(), video_path.resolve(), batch_path.resolve()),
                'invalid input file reuse')
        pair = (str(ev_path.resolve()), str(decision_path.resolve()))
        require(pair not in pairs, 'duplicate EV/decision pair')
        pairs.add(pair)
        for p in (ev_path, decision_path):
            key = str(p.resolve())
            digest = contract.sha256(p)
            require(key not in inputs or inputs[key][1] == digest, 'input changed during preflight')
            inputs[key] = (p, digest)
        ev_sha = inputs[str(ev_path.resolve())][1]
        decision_sha = inputs[str(decision_path.resolve())][1]
        plan = single.validate(summary, contract.read_json(ev_path),
                               contract.read_json(decision_path),
                               summary_sha, ev_sha, video_sha, duration)
        identity = (plan['table_id'], plan['hand_id'], plan['decision_pts_seconds_claim'])
        require(identity not in decision_keys, 'duplicate table/hand/decision timestamp')
        decision_keys.add(identity)
        tables.add(plan['table_id'])
        require(len(tables) <= 4, 'more than four tables')
        require(not (out_dir / (clip_id + '.mp4')).exists() and
                not (out_dir / (clip_id + '.mp4')).is_symlink() and
                not (out_dir / (clip_id + '.json')).exists() and
                not (out_dir / (clip_id + '.json')).is_symlink(), 'clip output already exists')
        plan['source_decision_sha256'] = decision_sha
        plans.append((clip_id, plan))
    require(all(contract.sha256(p) == digest for p, digest in inputs.values()),
            'input changed during preflight')
    # Confidence is a human claim, not a calibrated probability: never use it as
    # a multiplier of EV or as a mathematical certainty threshold.
    plans.sort(key=lambda x: (-x[1]['conditional_priority_score_chips_not_strategy_verdict'],
                              x[1]['decision_pts_seconds_claim'], x[1]['table_id'],
                              x[1]['hand_id'], x[0]))
    chosen, skipped = [], []
    for clip_id, plan in plans:
        gap = plan['conditional_priority_score_chips_not_strategy_verdict']
        if gap < batch['min_gap_chips']:
            reason = 'below_conditional_gap_threshold'
        elif any(plan['table_id'] == other['table_id'] and
                 plan['clip_start_seconds'] < other['clip_start_seconds'] + other['clip_duration_seconds'] and
                 other['clip_start_seconds'] < plan['clip_start_seconds'] + plan['clip_duration_seconds']
                 for _, other in chosen):
            reason = 'overlapping_clip_same_table'
        elif len(chosen) >= batch['max_clips']:
            reason = 'max_clips_reached'
        else:
            chosen.append((clip_id, plan))
            continue
        skipped.append({'clip_id': clip_id, 'table_id': plan['table_id'],
                        'hand_id': plan['hand_id'], 'reason': reason,
                        'conditional_gap_chips': gap})
    return chosen, skipped, inputs, batch, video_path, out_dir


def export(summary_path, video_path, batch_path, out_dir):
    chosen, skipped, inputs, batch, video, out_dir = prepare(
        summary_path, video_path, batch_path, out_dir)
    new_files = []
    try:
        rendered = []
        for clip_id, plan in chosen:
            mp4, report = single.render(video, plan, out_dir, clip_id)
            new_files.extend((mp4, report))
            require(single.video_duration(mp4) >= 0.5, 'invalid rendered MP4 duration')
            require(contract.read_json(report)['rendered_clip_sha256'] == contract.sha256(mp4),
                    'rendered MP4 digest mismatch')
            rendered.append({'clip_id': clip_id, 'table_id': plan['table_id'],
                             'hand_id': plan['hand_id'],
                             'decision_pts_seconds_claim': plan['decision_pts_seconds_claim'],
                             'conditional_gap_chips_not_regret': plan['conditional_priority_score_chips_not_strategy_verdict'],
                             'reviewer_confidence_claim_not_calibrated': plan['reviewer_confidence_claim_not_calibrated'],
                             'clip_filename': mp4.name, 'clip_report_filename': report.name,
                             'clip_sha256': contract.sha256(mp4),
                             'clip_start_seconds': plan['clip_start_seconds'],
                             'clip_duration_seconds': plan['clip_duration_seconds']})
        require(all(contract.sha256(p) == digest for p, digest in inputs.values()),
                'input changed during batch export')
        summary_sha = inputs[str(Path(summary_path).resolve())][1]
        video_sha = inputs[str(Path(video_path).resolve())][1]
        batch_sha = inputs[str(Path(batch_path).resolve())][1]
        ledger = {'schema_version': 1,
                  'status': 'offline_conditional_ev_batch_unverified_not_strategy_verdict',
                  'source_summary_sha256': summary_sha, 'source_video_sha256': video_sha,
                  'source_batch_sha256': batch_sha,
                  'candidate_count': len(batch['entries']), 'rendered_count': len(rendered),
                  'skipped_count': len(skipped), 'clips': rendered, 'skipped': skipped,
                  'ranking_method': 'descending conditional EV gap in chips; stable PTS/table/hand/ID ties',
                  'automatic_ocr_math_authorization': False,
                  'warning': ('Unverified manual cards, ranges, action and timestamp claims. '
                              'Conditional chip EV is not a strategy verdict. '
                              'Reviewer confidence is not calibrated; Monte Carlo intervals '
                              'exclude range, visual and model uncertainty.')}
        with tempfile.TemporaryDirectory(prefix='plo_batch_', dir=out_dir) as temp:
            tmp = Path(temp) / 'batch_report.json'
            tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                           encoding='utf-8')
            target = out_dir / 'batch_report.json'
            require(not target.exists() and not target.is_symlink(), 'batch report appeared during export')
            os.link(tmp, target)
            new_files.append(target)
        return ledger
    except BaseException:
        for path in reversed(new_files):
            path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('summary_json', 'video', 'batch_json', 'output_dir'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    ledger = export(args.summary_json, args.video, args.batch_json, args.output_dir)
    print(json.dumps({'status': ledger['status'], 'rendered': ledger['rendered_count'],
                      'skipped': ledger['skipped_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
