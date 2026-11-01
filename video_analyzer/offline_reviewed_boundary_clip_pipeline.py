"""Create subtitled MP4 clips from manually annotated, playback-relative hand intervals.

No poker inference or automatic decision selection. Human-review flags and
annotations are self-attested, not independently authenticated. Offline only.

CLI: python offline_reviewed_boundary_clip_pipeline.py VIDEO HANDS.json PICKS.json NEW_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import offline_reviewed_subtitled_batch_export as exporter

MAX_JSON_BYTES = 2 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_JSON_BYTES, 'invalid input JSON')
    return json.loads(path.read_text(encoding='utf-8'),
                      object_pairs_hook=unique_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def validate_and_build(hands, picks, video_sha, duration, dimensions):
    require(type(hands) is dict and set(hands) ==
            {'schema_version', 'status', 'recording_sha256', 'hands'} and
            type(hands['schema_version']) is int and hands['schema_version'] == 1 and
            hands['status'] == 'human_annotated_hand_boundaries' and
            hands['recording_sha256'] == video_sha and
            type(hands['hands']) is list and 1 <= len(hands['hands']) <= 512,
            'invalid human boundary manifest or recording hash')
    require(type(picks) is dict and set(picks) ==
            {'schema_version', 'time_basis', 'recording_sha256', 'selections'} and
            type(picks['schema_version']) is int and picks['schema_version'] == 1 and
            picks['time_basis'] == 'playback_seconds' and
            picks['recording_sha256'] == video_sha and
            type(picks['selections']) is list and
            1 <= len(picks['selections']) <= exporter.MAX_CLIPS,
            'invalid selections manifest or recording hash')
    intervals = []
    by_table = {t: [] for t in range(1, 5)}
    for index, row in enumerate(hands['hands']):
        require(type(row) is dict and set(row) ==
                {'table_id', 'start_seconds', 'end_seconds'}, 'invalid boundary fields')
        table, start, end = row['table_id'], row['start_seconds'], row['end_seconds']
        require(type(table) is int and 1 <= table <= 4 and
                type(start) in (int, float) and type(end) in (int, float) and
                math.isfinite(start) and math.isfinite(end) and
                0 <= start < end <= duration + 0.001 and end - start >= 0.05,
                'invalid hand interval or table')
        intervals.append(row)
        by_table[table].append((start, end, index))
    for rows in by_table.values():
        rows.sort()
        require(all(rows[i][0] >= rows[i - 1][1] for i in range(1, len(rows))),
                'overlapping hand boundaries on one table')
    clips = []
    indices = set()
    for pick in picks['selections']:
        require(type(pick) is dict and set(pick) ==
                {'review_id', 'hand_index', 'table_id', 'explanation',
                 'human_reviewed', 'crop'}, 'invalid selection fields')
        idx = pick['hand_index']
        require(type(idx) is int and 0 <= idx < len(intervals) and idx not in indices,
                'invalid or repeated hand index')
        indices.add(idx)
        row = intervals[idx]
        require(type(pick['table_id']) is int and pick['table_id'] == row['table_id'],
                'selection table does not match hand')
        clips.append({'review_id': pick['review_id'], 'table_id': row['table_id'],
                      'start_seconds': row['start_seconds'],
                      'end_seconds': row['end_seconds'],
                      'explanation': pick['explanation'],
                      'human_reviewed': pick['human_reviewed'],
                      'crop': pick['crop']})
    manifest = {'schema_version': 1, 'time_basis': 'playback_seconds',
                'recording_sha256': video_sha, 'clips': clips}
    exporter.validate_manifest(manifest, video_sha, duration, dimensions)
    return manifest


def run(recording, hands_json, selections_json, new_output_dir,
        *, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    video, hands_path, picks_path, output = map(
        Path, (recording, hands_json, selections_json, new_output_dir))
    inputs = (video, hands_path, picks_path)
    require(all(p.is_file() and not p.is_symlink() and p.stat().st_size > 0
                for p in inputs) and len({str(p.resolve()) for p in inputs}) == 3,
            'unsafe or overlapping inputs')
    # The downstream exporter changes cwd for subtitle filters: use absolute video.
    video = video.resolve()
    inputs = (video, hands_path, picks_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(not p.resolve().is_relative_to(output.resolve()) for p in inputs),
            'output must be a new disjoint directory')
    hashes = [digest(p) for p in inputs]
    duration = exporter.duration_seconds(video, ffprobe)
    dimensions = exporter.video_dimensions(video, ffprobe)
    manifest = validate_and_build(load(hands_path), load(picks_path),
                                  hashes[0], duration, dimensions)
    with tempfile.TemporaryDirectory(prefix='.plo_reviewed_hands_', dir=output.parent) as tmp:
        stage = Path(tmp) / 'published'
        stage.mkdir()
        review_path = stage / 'review_manifest.json'
        review_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                          allow_nan=False) + '\n', encoding='utf-8')
        result = exporter.export(video, review_path, stage / 'clips',
                                 ffmpeg=ffmpeg, ffprobe=ffprobe)
        require(result.get('status') == 'offline_human_reviewed_clips_exported' and
                len(result.get('clips', [])) == len(manifest['clips']) and
                result.get('equity_or_ev_verified') is False and
                result.get('poker_accuracy_verified') is False,
                'unexpected exporter result')
        report = {'schema_version': 1,
                  'status': 'offline_reviewed_boundary_clip_export_diagnostics_only',
                  'recording_sha256_verified': hashes[0],
                  'human_boundary_json_sha256': hashes[1],
                  'selection_json_sha256': hashes[2],
                  'generated_review_manifest_sha256': digest(review_path),
                  'clip_export_report_sha256': digest(stage / 'clips' / 'export_report.json'),
                  'clip_count': len(manifest['clips']),
                  'hand_indices': [p['hand_index'] for p in load(picks_path)['selections']],
                  'human_annotations_authenticated': False,
                  'explanations_independently_verified': False,
                  'equity_or_ev_verified': False,
                  'automatic_hand_detection_performed': False,
                  'warning': 'Boundaries, review flags and explanations are user supplied; no poker accuracy claim.'}
        (stage / 'pipeline_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        require([digest(p) for p in inputs] == hashes and
                not output.exists() and not output.is_symlink(),
                'inputs changed or output appeared during processing')
        os.rename(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('human_hand_boundaries_json')
    parser.add_argument('reviewed_selections_json')
    parser.add_argument('new_output_directory')
    args = parser.parse_args(argv)
    report = run(args.recording, args.human_hand_boundaries_json,
                 args.reviewed_selections_json, args.new_output_directory)
    print(json.dumps({'status': report['status'], 'clips': report['clip_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
