"""Offline dense re-sampling of *visual-change candidates*, never poker-hand inference.

Usage: python offline_adaptive_change_refinement.py VIDEO REGIONS_JSON INGEST_DIR CHANGE_REPORT_JSON NEW_OUTPUT_DIR
Requires FFmpeg; no network, OCR, live capture, equity, or poker advice.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import tempfile

from offline_video_ingest_probe import (extract_sample_frame, nominal_fps, probe,
                                        regions_from_json, require, sha256)
from offline_sampled_visual_change import (compare_frames, decode_gray, frame_records,
                                           read_manifest, unique_keys)

MAX_EVENTS = 64
MAX_NEW_FRAMES = 1024


def read_changes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= 4 * 1024 * 1024, 'Invalid change report')
    data = json.loads(path.read_text('utf-8'), object_pairs_hook=unique_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    require(type(data) is dict and data.get('schema_version') == 1 and
            data.get('analysis_status') == 'offline_visual_change_candidates_only' and
            type(data.get('candidate_intervals')) is list and
            len(data['candidate_intervals']) <= MAX_EVENTS and
            type(data.get('detector')) is dict, 'Invalid change report schema')
    threshold = data['detector'].get('threshold')
    coverage = data['detector'].get('minimum_changed_pixel_fraction')
    require(type(threshold) in (int, float) and math.isfinite(threshold) and
            0.01 <= threshold <= 0.9 and type(coverage) in (int, float) and
            math.isfinite(coverage) and 0 <= coverage <= 1, 'Invalid detector thresholds')
    return data


def schedule(start, end, step, fps):
    """Strictly interior timestamps, aligned to nominal FPS when known."""
    require(0 <= start < end and end - start <= 60, 'Candidate interval outside refinement limit')
    if fps:
        first = math.floor(start * fps + 1e-8) + 1
        last = math.ceil(end * fps - 1e-8)
        increment = max(1, math.ceil(step * fps))
        return [round(i / fps, 6) for i in range(first, last, increment)
                if start + 1e-5 < i / fps < end - 1e-5]
    return [round(start + i * step, 6) for i in range(1, math.ceil((end-start) / step))
            if start + i * step < end - 1e-5]


def refine(video, regions_json, ingest_dir, changes_json, output_dir, step=0.5):
    video, regions_json, ingest_dir, changes_json, output_dir = map(
        Path, (video, regions_json, ingest_dir, changes_json, output_dir))
    require(type(step) in (int, float) and math.isfinite(step) and 0.25 <= step <= 5,
            'Invalid dense sampling step')
    require(all(p.is_file() and not p.is_symlink() for p in (video, regions_json)),
            'Invalid source inputs')
    require(output_dir.parent.is_dir() and not output_dir.exists() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
            'Output directory must be new and safe')
    manifest, manifest_hash = read_manifest(ingest_dir)
    changes = read_changes(changes_json)
    report_hash = sha256(changes_json)
    require(changes.get('ingest_manifest_sha256') == manifest_hash and
            changes.get('source_sha256') == manifest['source_sha256'] and
            changes.get('regions_config_sha256') == manifest['regions_config_sha256'],
            'Change report does not match ingest evidence')
    require(sha256(video) == manifest['source_sha256'] and
            sha256(regions_json) == manifest['regions_config_sha256'],
            'Source video or region configuration changed')
    media = probe(video)
    require(media['width'] == manifest['media']['width'] and
            media['height'] == manifest['media']['height'] and
            abs(media['duration_seconds'] - manifest['media']['duration_seconds']) < 0.01,
            'Video metadata mismatch')
    regions = regions_from_json(regions_json, media['width'], media['height'])
    require(regions == manifest['regions'], 'Region geometry mismatch')
    grouped = frame_records(ingest_dir, manifest)
    samples = {(tid, r['file']): r for tid, rs in grouped.items() for r in rs}
    fps = nominal_fps(media['frame_rate_reported'])
    planned = []
    for index, event in enumerate(changes['candidate_intervals']):
        require(type(event) is dict and event.get('classification') ==
                'unlocalized_visual_change_for_manual_review' and
                event.get('hand_boundary_confidence') is None,
                'Not a visual-change candidate')
        tid = event.get('table_id')
        require(type(tid) is int and tid in grouped, 'Invalid candidate table')
        a, b = event.get('previous_file'), event.get('current_file')
        require(type(a) is str and type(b) is str and a != b and
                (tid, a) in samples and (tid, b) in samples, 'Invalid candidate endpoints')
        start, end = samples[tid, a]['pts'], samples[tid, b]['pts']
        require(type(event.get('earliest_possible_change_seconds')) in (int, float) and
                type(event.get('latest_possible_change_seconds')) in (int, float) and
                abs(event['earliest_possible_change_seconds'] - start) < 1e-5 and
                abs(event['latest_possible_change_seconds'] - end) < 1e-5,
                'Candidate timestamps differ from verified sampled frames')
        times = schedule(start, end, step, fps)
        planned.append((index, event, start, end, times))
    require(sum(len(item[4]) for item in planned) <= MAX_NEW_FRAMES,
            'Dense extraction budget exceeded')
    region_map = {r['table_id']: r for r in regions}
    refined = []
    with tempfile.TemporaryDirectory(prefix='.plo_refine_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        for index, event, start, end, times in planned:
            tid = event['table_id']
            r = region_map[tid]
            crop = f"crop={r['width']}:{r['height']}:{r['x']}:{r['y']}"
            records = [{'pts': start, 'file': event['previous_file'],
                        'path': ingest_dir / event['previous_file'], 'origin': 'sparse'}]
            for j, timestamp in enumerate(times):
                name = f'refine_{index:03d}_{j:03d}.jpg'
                path = stage / name
                decoded = extract_sample_frame(video, crop, timestamp, path,
                                               media['frame_rate_reported'])
                pts = decoded['actual_frame_timestamp_seconds']
                require(start - 0.01 <= pts <= end + 0.01,
                        'Decoded frame outside candidate interval')
                records.append({'pts': pts, 'file': name, 'path': path,
                                'sha256': sha256(path), 'origin': 'dense',
                                'requested_seconds': timestamp})
            records.append({'pts': end, 'file': event['current_file'],
                            'path': ingest_dir / event['current_file'], 'origin': 'sparse'})
            records.sort(key=lambda x: (x['pts'], x['origin'] != 'sparse'))
            transitions = []
            prior, prior_gray = None, None
            for item in records:
                gray = decode_gray(item['path'])
                if prior is not None and item['pts'] > prior['pts'] + 1e-5:
                    difference, coverage = compare_frames(prior_gray, gray)
                    if difference >= changes['detector']['threshold'] and coverage >= changes['detector']['minimum_changed_pixel_fraction']:
                        transitions.append({'from_seconds': prior['pts'], 'to_seconds': item['pts'],
                                            'mean_difference': difference, 'changed_fraction': coverage})
                prior, prior_gray = item, gray
            refined.append({'source_candidate_index': index, 'table_id': tid,
                            'original_interval_seconds': [start, end],
                            'new_frames': [dict((k, v) for k, v in item.items() if k != 'path')
                                           for item in records if item['origin'] == 'dense'],
                            'visual_transition_brackets': transitions,
                            'hand_boundary_confidence': None,
                            'classification': 'visual_transitions_not_poker_hand_boundaries'})
        report = {'schema_version': 1, 'analysis_status': 'offline_dense_visual_refinement_only',
                  'source_sha256': manifest['source_sha256'],
                  'ingest_manifest_sha256': manifest_hash,
                  'change_report_sha256': report_hash,
                  'step_seconds': step, 'refinements': refined,
                  'hands_reconstructed': False, 'ocr_performed': False,
                  'equity_ev_computed': False,
                  'warning': 'Visual transitions are uncalibrated; no poker-hand boundaries inferred.'}
        (stage / 'dense_refinement.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', 'utf-8')
        require(sha256(video) == manifest['source_sha256'] and
                sha256(regions_json) == manifest['regions_config_sha256'] and
                sha256(ingest_dir / 'manifest.json') == manifest_hash and
                sha256(changes_json) == report_hash, 'Inputs changed during refinement')
        require(not output_dir.exists(), 'Output path appeared during refinement')
        os.rename(stage, output_dir)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('video', 'regions_json', 'ingest_dir', 'changes_json', 'new_output_dir'):
        parser.add_argument(arg)
    parser.add_argument('--step', type=float, default=0.5)
    args = parser.parse_args(argv)
    result = refine(args.video, args.regions_json, args.ingest_dir,
                    args.changes_json, args.new_output_dir, args.step)
    print(json.dumps({'candidates': len(result['refinements']),
                      'new_frames': sum(len(x['new_frames']) for x in result['refinements'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
