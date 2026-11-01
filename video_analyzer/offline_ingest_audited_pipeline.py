"""Offline ingest -> full PTS/SHA audit -> bounded source-pixel spot check.

Usage: python offline_ingest_audited_pipeline.py VIDEO REGIONS_JSON NEW_OUTPUT_DIR
           [--interval-seconds 30] [--pixel-checks 32]

This is an evidence-integrity pipeline, NOT OCR, hand recognition, or EV advice.
The complete PTS/hash audit covers every crop. The pixel audit checks only a
stratified subset, and its report states the exact coverage and limitations.
No source files are modified. A failed stage never publishes an output folder.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from offline_video_ingest_probe import (build, nominal_fps, probe, regions_from_json,
                                        sample_times, sha256, require)
from offline_ingest_pts_audit import audit, MAX_SAMPLES
from offline_ingest_roi_pixel_audit import verify, MAX_CHECKS


def choose_spotcheck(samples, tables, budget):
    """Choose deterministic, temporally spread samples for every table."""
    require(type(budget) is int and len(tables) <= budget <= MAX_CHECKS,
            'pixel check budget must cover each table and be <= 64')
    grouped = {table: [] for table in tables}
    for s in samples:
        require(type(s) is dict and type(s.get('table_id')) is int and
                s['table_id'] in grouped, 'invalid table in samples')
        grouped[s['table_id']].append(s)
    require(all(grouped.values()), 'missing samples for a table')
    selected = []
    base, extra = divmod(min(budget, len(samples)), len(tables))
    for i, table in enumerate(sorted(tables)):
        entries = grouped[table]
        quota = min(len(entries), base + (i < extra))
        if quota == 1:
            indices = [len(entries) // 2]
        else:
            indices = [round(j * (len(entries) - 1) / (quota - 1))
                       for j in range(quota)]
        selected.extend(entries[j] for j in indices)
    require(len({s['file'] for s in selected}) == len(selected),
            'duplicate pixel check samples')
    return selected


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run(video, regions_json, new_output_dir, interval_seconds=30.0, pixel_checks=32):
    video, regions_json, output = map(Path, (video, regions_json, new_output_dir))
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output.name),
            'output must be a new safe directory')
    require(len({str(p.resolve()) for p in (video, regions_json, output)}) == 3,
            'input/output paths must differ')
    # Cheap preflight before potentially hundreds of FFmpeg subprocesses.
    media = probe(video)
    tables = regions_from_json(regions_json, media['width'], media['height'])
    require(type(pixel_checks) is int and len(tables) <= pixel_checks <= MAX_CHECKS,
            'invalid pixel check budget')
    times = sample_times(media['duration_seconds'], media['frame_rate_reported'], interval_seconds)
    require(len(times) * len(tables) <= MAX_SAMPLES,
            'sampling would exceed bounded PTS audit capacity')
    with tempfile.TemporaryDirectory(prefix='.plo_audited_', dir=output.parent) as temp:
        stage = Path(temp)
        ingest = stage / 'ingest'
        manifest = build(video, regions_json, ingest, interval_seconds)
        full_pts = audit(video, ingest)
        require(full_pts['sample_count'] == len(manifest['samples']),
                'incomplete full PTS audit')
        selected = choose_spotcheck(manifest['samples'],
                                    [t['table_id'] for t in tables], pixel_checks)
        with tempfile.TemporaryDirectory(prefix='.pixel_subset_', dir=stage) as subset_temp:
            subset = Path(subset_temp)
            subset_manifest = dict(manifest)
            subset_manifest['samples'] = selected
            write_json(subset / 'manifest.json', subset_manifest)
            for s in selected:
                shutil.copyfile(ingest / s['file'], subset / s['file'])
            pixels = verify(video, subset)
        require(pixels['samples_checked'] == len(selected), 'incomplete pixel audit')
        require(pixels['source_sha256'] == full_pts['source_sha256'],
                'audits disagree on source hash')
        require(sha256(regions_json) == manifest['regions_config_sha256'],
                'region configuration changed during processing')
        require(sha256(video) == manifest['source_sha256'],
                'video changed during processing')
        write_json(stage / 'pts_audit.json', full_pts)
        write_json(stage / 'pixel_spotcheck.json', pixels)
        summary = {
            'schema_version': 1,
            'status': 'offline_ingest_full_pts_and_partial_pixel_audit_not_ocr',
            'source_sha256': manifest['source_sha256'],
            'tables': len(tables),
            'total_crops_pts_hash_audited': full_pts['sample_count'],
            'crops_pixel_checked': pixels['samples_checked'],
            'pixel_coverage_fraction': round(pixels['samples_checked'] / full_pts['sample_count'], 6),
            'pixel_check_selection': 'deterministic_stratified_by_table_and_time',
            'pixel_checked_files': [s['file'] for s in selected],
            'vfr_observed': full_pts['variable_frame_intervals_observed'],
            'manifest_sha256': sha256(ingest / 'manifest.json'),
            'pts_audit_sha256': sha256(stage / 'pts_audit.json'),
            'pixel_spotcheck_sha256': sha256(stage / 'pixel_spotcheck.json'),
            'ocr_verified': False, 'hands_reconstructed': False,
            'equity_ev_authorized': False, 'live_integration': False,
            'limitations': [
                'Every crop is SHA/PTS audited; only listed crops are source-pixel checked.',
                'Pixel similarity is not proof of cards, hands, actions, or table identity.',
                'Sparse sampling misses events between frames; no real-video accuracy measured.',
                'Long recordings may require substantial FFmpeg decoding time and storage.',
                'No OCR or equity/EV is authorized by this report.']}
        write_json(stage / 'chain_report.json', summary)
        require(not output.exists(), 'output appeared during processing')
        # Rename a prepared folder, never leave partially published evidence.
        os.rename(stage, output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('regions_json')
    parser.add_argument('new_output_dir')
    parser.add_argument('--interval-seconds', type=float, default=30.0)
    parser.add_argument('--pixel-checks', type=int, default=32)
    args = parser.parse_args(argv)
    result = run(args.video, args.regions_json, args.new_output_dir,
                 args.interval_seconds, args.pixel_checks)
    print(json.dumps({'tables': result['tables'],
                      'full_pts_checks': result['total_crops_pts_hash_audited'],
                      'pixel_checks': result['crops_pixel_checked']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
