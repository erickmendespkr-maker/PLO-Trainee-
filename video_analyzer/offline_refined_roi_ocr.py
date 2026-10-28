"""Offline OCR *proposals* from SHA-verified sparse/dense visual-change frames.

This is not poker-hand recognition. A user selects each bounded ROI; OCR results
remain unverified and cannot be used as cards, actions, ranges, equity or EV.

Usage:
 python offline_refined_roi_ocr.py RECORDING REGIONS_JSON INGEST_DIR \
   CHANGES_JSON REFINED_DIR ROI_TASKS_JSON NEW_OUTPUT_DIR

ROI task manifest v1:
 {"schema_version":1, "source_ingest_manifest_sha256":"...",
  "source_dense_refinement_sha256":"...", "tasks":[
   {"table_id":1,"frame_file":"refine_000_000.jpg","field":"pot",
    "roi":{"x":0,"y":0,"width":80,"height":40}}]}
No network, live capture, OCR-to-fact promotion, or automatic betting advice.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from offline_video_ingest_probe import regions_from_json, require, sha256
from offline_sampled_visual_change import frame_records, read_manifest, unique_keys
from offline_adaptive_change_refinement import read_changes

FIELDS = frozenset({'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'})
MAX_TASKS = 64
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}\Z')
DENSE_NAME = re.compile(r'refine_(\d{3})_(\d{3})\.jpg\Z')


def load_json(path, limit=MAX_JSON_BYTES):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= limit, 'Invalid or oversized JSON input')
    try:
        return json.loads(path.read_text('utf-8'), object_pairs_hook=unique_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Malformed JSON input') from exc


def parse_tsv(raw):
    require(len(raw) <= 1024 * 1024, 'Oversized OCR output')
    rows = csv.DictReader(StringIO(raw.decode('utf-8', 'replace')), delimiter='\t')
    require(rows.fieldnames is not None and {'text', 'conf'} <= set(rows.fieldnames),
            'Invalid Tesseract TSV')
    words, confidences = [], []
    for row in rows:
        word = (row.get('text') or '').strip()
        if not word:
            continue
        require(len(word) <= 256 and all(ord(c) >= 32 for c in word),
                'Unsafe OCR token')
        try:
            confidence = float(row.get('conf', ''))
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid OCR confidence') from exc
        require(math.isfinite(confidence), 'Nonfinite OCR confidence')
        if confidence < 0:
            continue
        require(confidence <= 100, 'OCR confidence outside engine scale')
        words.append(word)
        confidences.append(confidence / 100)
    return (' '.join(words)[:512], len(words),
            round(sum(confidences) / len(confidences), 6) if confidences else None)


def _valid_sha(value):
    return type(value) is str and bool(HEX.fullmatch(value))


def evidence_index(ingest_dir, changes_json, refined_dir):
    """Revalidate the full hash-linked sparse/dense evidence chain."""
    ingest_dir, changes_json, refined_dir = map(Path, (ingest_dir, changes_json, refined_dir))
    require(ingest_dir.is_dir() and not ingest_dir.is_symlink() and
            refined_dir.is_dir() and not refined_dir.is_symlink(), 'Unsafe evidence directories')
    manifest, manifest_sha = read_manifest(ingest_dir)
    grouped = frame_records(ingest_dir, manifest)
    changes = read_changes(changes_json)
    changes_sha = sha256(changes_json)
    dense_path = refined_dir / 'dense_refinement.json'
    dense = load_json(dense_path)
    dense_sha = sha256(dense_path)
    require(changes.get('ingest_manifest_sha256') == manifest_sha and
            changes.get('source_sha256') == manifest['source_sha256'] and
            changes.get('regions_config_sha256') == manifest['regions_config_sha256'],
            'Change report source binding mismatch')
    require(type(dense) is dict and dense.get('schema_version') == 1 and
            dense.get('analysis_status') == 'offline_dense_visual_refinement_only' and
            dense.get('ingest_manifest_sha256') == manifest_sha and
            dense.get('change_report_sha256') == changes_sha and
            dense.get('source_sha256') == manifest['source_sha256'] and
            type(dense.get('refinements')) is list and
            len(dense['refinements']) == len(changes['candidate_intervals']) <= 64,
            'Dense report source binding mismatch')
    sparse = {(tid, r['file']): r for tid, rs in grouped.items() for r in rs}
    images = {}
    for i, (event, item) in enumerate(zip(changes['candidate_intervals'], dense['refinements'])):
        require(type(event) is dict and type(item) is dict and
                item.get('source_candidate_index') == i and
                type(item.get('table_id')) is int and
                item['table_id'] == event.get('table_id') and
                item.get('classification') == 'visual_transitions_not_poker_hand_boundaries' and
                item.get('hand_boundary_confidence') is None,
                'Invalid dense refinement identity')
        tid = item['table_id']
        a, b = event.get('previous_file'), event.get('current_file')
        require((tid, a) in sparse and (tid, b) in sparse,
                'Dense refinement references unknown sparse samples')
        start, end = sparse[(tid, a)]['pts'], sparse[(tid, b)]['pts']
        bounds = item.get('original_interval_seconds')
        require(type(bounds) is list and len(bounds) == 2 and
                all(type(v) in (int, float) and math.isfinite(v) for v in bounds) and
                abs(bounds[0] - start) < 1e-5 and abs(bounds[1] - end) < 1e-5 and
                0 <= start < end <= manifest['media']['duration_seconds'] + 0.1,
                'Invalid dense interval bounds')
        for name in (a, b):
            record = sparse[(tid, name)]
            images[(tid, name)] = {'path': record['path'], 'sha256': record['sha256'],
                                   'pts': record['pts'], 'kind': 'sparse'}
        new_frames = item.get('new_frames')
        require(type(new_frames) is list and len(new_frames) <= 1024,
                'Invalid dense frame list')
        for j, record in enumerate(new_frames):
            require(type(record) is dict and record.get('origin') == 'dense' and
                    type(record.get('file')) is str and
                    bool(DENSE_NAME.fullmatch(record['file'])) and
                    record['file'] == f'refine_{i:03d}_{j:03d}.jpg' and
                    _valid_sha(record.get('sha256')) and
                    type(record.get('pts')) in (int, float) and
                    math.isfinite(record['pts']) and start - 0.01 <= record['pts'] <= end + 0.01 and
                    type(record.get('requested_seconds')) in (int, float) and
                    math.isfinite(record['requested_seconds']), 'Invalid dense frame identity')
            name = record['file']
            require((tid, name) not in images, 'Duplicate dense frame identity')
            path = refined_dir / name
            require(path.is_file() and not path.is_symlink() and
                    0 < path.stat().st_size <= MAX_IMAGE_BYTES and
                    sha256(path) == record['sha256'], 'Dense frame missing or modified')
            images[(tid, name)] = {'path': path, 'sha256': record['sha256'],
                                   'pts': record['pts'], 'kind': 'dense'}
    return manifest, manifest_sha, changes_sha, dense_sha, images


def run_ocr(source, roi, target):
    x, y, w, h = (roi[k] for k in ('x', 'y', 'width', 'height'))
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error',
               '-i', str(source), '-vf', f'crop={w}:{h}:{x}:{y}:exact=1,scale=iw*2:ih*2',
               '-frames:v', '1', '-update', '1', '-y', str(target)]
    try:
        proc = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=30, check=False)
        require(proc.returncode == 0 and target.is_file() and
                0 < target.stat().st_size <= MAX_IMAGE_BYTES,
                'FFmpeg ROI extraction failed')
        ocr = subprocess.run(['tesseract', str(target), 'stdout', '--psm', '6', 'tsv'],
                             capture_output=True, stdin=subprocess.DEVNULL,
                             timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Offline OCR process unavailable or timed out') from exc
    require(ocr.returncode == 0, 'Tesseract OCR failed')
    return parse_tsv(ocr.stdout)


def scan(recording, regions_json, ingest_dir, changes_json, refined_dir,
         tasks_json, output_dir):
    recording, regions_json, ingest_dir, changes_json, refined_dir, tasks_json, output_dir = map(
        Path, (recording, regions_json, ingest_dir, changes_json, refined_dir, tasks_json, output_dir))
    require(recording.is_file() and not recording.is_symlink() and
            regions_json.is_file() and not regions_json.is_symlink(), 'Unsafe recording or regions')
    require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink() and
            not output_dir.exists() and not output_dir.is_symlink() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
            'Output directory must be new and safe')
    require(not any(output_dir.resolve().is_relative_to(p.resolve()) for p in
                    (ingest_dir, refined_dir)), 'Output cannot be inside evidence directories')
    manifest, manifest_sha, changes_sha, dense_sha, images = evidence_index(
        ingest_dir, changes_json, refined_dir)
    require(sha256(recording) == manifest['source_sha256'] and
            sha256(regions_json) == manifest['regions_config_sha256'],
            'Recording or region configuration changed')
    region_list = regions_from_json(regions_json, manifest['media']['width'],
                                    manifest['media']['height'])
    require(region_list == manifest['regions'], 'Table regions differ from ingest manifest')
    regions = {r['table_id']: r for r in region_list}
    tasks = load_json(tasks_json, 64 * 1024)
    tasks_sha = sha256(tasks_json)
    require(type(tasks) is dict and set(tasks) ==
            {'schema_version', 'source_ingest_manifest_sha256',
             'source_dense_refinement_sha256', 'tasks'} and
            type(tasks['schema_version']) is int and tasks['schema_version'] == 1 and
            tasks['source_ingest_manifest_sha256'] == manifest_sha and
            tasks['source_dense_refinement_sha256'] == dense_sha and
            type(tasks['tasks']) is list and 1 <= len(tasks['tasks']) <= MAX_TASKS,
            'Invalid ROI task manifest or provenance')
    planned, seen = [], set()
    for index, task in enumerate(tasks['tasks']):
        require(type(task) is dict and set(task) ==
                {'table_id', 'frame_file', 'field', 'roi'}, 'Unexpected ROI task fields')
        tid, name, field, roi = (task[k] for k in ('table_id', 'frame_file', 'field', 'roi'))
        require(type(tid) is int and tid in regions and type(name) is str and
                (tid, name) in images and type(field) is str and field in FIELDS and
                (tid, name, field) not in seen, 'Invalid or duplicate ROI task identity')
        seen.add((tid, name, field))
        require(type(roi) is dict and set(roi) == {'x', 'y', 'width', 'height'} and
                all(type(v) is int for v in roi.values()), 'Invalid ROI coordinates')
        x, y, w, h = (roi[k] for k in ('x', 'y', 'width', 'height'))
        region = regions[tid]
        require(x >= 0 and y >= 0 and 8 <= w <= region['width'] and
                8 <= h <= region['height'] and x + w <= region['width'] and
                y + h <= region['height'], 'ROI outside table region')
        planned.append((index, tid, name, field, roi, images[(tid, name)]))
    proposals = []
    with tempfile.TemporaryDirectory(prefix='.plo_roi_ocr_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        for index, tid, name, field, roi, frame in planned:
            require(sha256(frame['path']) == frame['sha256'],
                    'Frame modified before OCR')
            output_name = f'roi_{index:03d}.png'
            png = stage / output_name
            text, words, confidence = run_ocr(frame['path'], roi, png)
            require(sha256(frame['path']) == frame['sha256'],
                    'Frame modified during OCR')
            proposals.append({'table_id': tid, 'frame_file': name,
                              'frame_kind': frame['kind'],
                              'decoded_source_pts_seconds': frame['pts'],
                              'source_frame_sha256': frame['sha256'],
                              'field': field, 'roi': roi, 'roi_png': output_name,
                              'roi_png_sha256': sha256(png),
                              'raw_ocr_text': text, 'word_count': words,
                              'tesseract_mean_word_confidence_uncalibrated': confidence,
                              'parsed_candidate': None, 'status': 'needs_manual_review'})
        report = {'schema_version': 1,
                  'analysis_status': 'offline_refined_roi_ocr_proposals_only',
                  'source_sha256': manifest['source_sha256'],
                  'source_ingest_manifest_sha256': manifest_sha,
                  'source_change_report_sha256': changes_sha,
                  'source_dense_refinement_sha256': dense_sha,
                  'source_roi_tasks_sha256': tasks_sha,
                  'engine': 'tesseract_psm6_on_ffmpeg_user_selected_roi',
                  'engine_confidence_is_calibrated_probability': False,
                  'requires_manual_review': True, 'ready_for_equity_or_ev': False,
                  'hands_reconstructed': False, 'proposals': proposals,
                  'warning': 'OCR tokens and engine confidence are unverified; no poker facts or hand boundaries inferred.'}
        (stage / 'roi_ocr_proposals.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')
        require(sha256(recording) == manifest['source_sha256'] and
                sha256(regions_json) == manifest['regions_config_sha256'] and
                sha256(tasks_json) == tasks_sha and
                sha256(changes_json) == changes_sha and
                sha256(refined_dir / 'dense_refinement.json') == dense_sha and
                sha256(ingest_dir / 'manifest.json') == manifest_sha,
                'Input changed during OCR')
        # Reverify all sparse and dense frame hashes before publication.
        evidence_index(ingest_dir, changes_json, refined_dir)
        require(not output_dir.exists(), 'Output path appeared during OCR')
        os.rename(stage, output_dir)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('recording', 'regions_json', 'ingest_dir', 'changes_json',
                'refined_dir', 'roi_tasks_json', 'new_output_dir'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    result = scan(args.recording, args.regions_json, args.ingest_dir,
                  args.changes_json, args.refined_dir, args.roi_tasks_json,
                  args.new_output_dir)
    print(json.dumps({'proposals': len(result['proposals']),
                      'status': result['analysis_status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
