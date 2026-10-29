"""Read-only, deterministic source-video -> JPEG frame -> OCR ROI PNG replay audit.

Usage:
 python offline_ocr_source_replay_audit.py VIDEO REGIONS_JSON INGEST_DIR \
   CHANGES_JSON REFINED_DIR TASKS_JSON OCR_DIR

Re-extracts only frames referenced by OCR proposals using the original FFmpeg
sampling method, then re-renders the exact ROI PNGs. Exact byte equality is
expected with the same FFmpeg/JPEG/PNG build and options; a mismatch can also
reflect codec/toolchain drift, not necessarily tampering. No OCR interpretation,
hand reconstruction, equity or EV is performed. Does not alter evidence files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from offline_video_ingest_probe import extract_sample_frame, regions_from_json
from offline_refined_roi_ocr import evidence_index, load_json

SHA = re.compile(r'[0-9a-f]{64}\Z')
FIELDS = frozenset({'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'})
MAX_TASKS = 64
MAX_PNG_BYTES = 12 * 1024 * 1024


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha_valid(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def pts_valid(value):
    return type(value) in (int, float) and math.isfinite(value)


def replay_roi(frame, roi, output):
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error',
               '-i', str(frame), '-vf',
               f"crop={roi['width']}:{roi['height']}:{roi['x']}:{roi['y']}:exact=1,scale=iw*2:ih*2",
               '-frames:v', '1', '-update', '1', '-y', str(output)]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg ROI replay unavailable') from exc
    need(result.returncode == 0 and output.is_file()
         and 8 <= output.stat().st_size <= MAX_PNG_BYTES,
         'FFmpeg ROI replay failed')


def audit(video, regions_json, ingest_dir, changes_json, refined_dir,
          tasks_json, ocr_dir):
    video, regions_json, ingest_dir, changes_json, refined_dir, tasks_json, ocr_dir = map(
        Path, (video, regions_json, ingest_dir, changes_json, refined_dir, tasks_json, ocr_dir))
    for path in (video, regions_json, changes_json, tasks_json):
        need(path.is_file() and not path.is_symlink(), 'unsafe input file')
    need(ocr_dir.is_dir() and not ocr_dir.is_symlink(), 'unsafe OCR directory')
    manifest, manifest_sha, changes_sha, dense_sha, frames = evidence_index(
        ingest_dir, changes_json, refined_dir)
    need(digest(video) == manifest['source_sha256']
         and digest(regions_json) == manifest['regions_config_sha256'],
         'source video or region configuration hash mismatch')
    regions_list = regions_from_json(regions_json, manifest['media']['width'],
                                     manifest['media']['height'])
    need(regions_list == manifest['regions'], 'regions differ from ingest manifest')
    regions = {r['table_id']: r for r in regions_list}
    tasks = load_json(tasks_json, 64 * 1024)
    ocr_path = ocr_dir / 'roi_ocr_proposals.json'
    ocr = load_json(ocr_path)
    ocr_sha = digest(ocr_path)
    need(type(tasks) is dict and set(tasks) ==
         {'schema_version', 'source_ingest_manifest_sha256',
          'source_dense_refinement_sha256', 'tasks'}
         and type(tasks['schema_version']) is int and tasks['schema_version'] == 1
         and tasks['source_ingest_manifest_sha256'] == manifest_sha
         and tasks['source_dense_refinement_sha256'] == dense_sha
         and type(tasks['tasks']) is list
         and 1 <= len(tasks['tasks']) <= MAX_TASKS, 'invalid ROI tasks manifest')
    need(type(ocr) is dict and type(ocr.get('schema_version')) is int
         and ocr['schema_version'] == 1
         and ocr.get('analysis_status') == 'offline_refined_roi_ocr_proposals_only'
         and ocr.get('source_sha256') == manifest['source_sha256']
         and ocr.get('source_ingest_manifest_sha256') == manifest_sha
         and ocr.get('source_change_report_sha256') == changes_sha
         and ocr.get('source_dense_refinement_sha256') == dense_sha
         and ocr.get('source_roi_tasks_sha256') == digest(tasks_json)
         and ocr.get('hands_reconstructed') is False
         and ocr.get('ready_for_equity_or_ev') is False
         and ocr.get('requires_manual_review') is True
         and ocr.get('engine_confidence_is_calibrated_probability') is False
         and type(ocr.get('proposals')) is list
         and len(ocr['proposals']) == len(tasks['tasks']),
         'invalid OCR provenance or analysis status')

    # Use recorded requested timestamps for replay; PTS is independently checked.
    sparse = {(s['table_id'], s['file']): s for s in manifest['samples']}
    dense = load_json(refined_dir / 'dense_refinement.json')
    dense_lookup = {}
    for item in dense['refinements']:
        for record in item['new_frames']:
            key = (item['table_id'], record['file'])
            need(key not in dense_lookup, 'duplicate dense frame')
            dense_lookup[key] = record

    seen_tasks = set()
    needed_frames = {}
    roi_plan = []
    for index, (task, proposal) in enumerate(zip(tasks['tasks'], ocr['proposals'])):
        need(type(task) is dict and set(task) ==
             {'table_id', 'frame_file', 'field', 'roi'}
             and type(proposal) is dict, 'invalid task/proposal entry')
        tid, name, field, roi = (task[k] for k in ('table_id', 'frame_file', 'field', 'roi'))
        key = (tid, name)
        need(type(tid) is int and tid in regions
             and type(name) is str and key in frames
             and type(field) is str and field in FIELDS
             and (tid, name, field) not in seen_tasks,
             'unknown or duplicate OCR task')
        seen_tasks.add((tid, name, field))
        need(type(roi) is dict and set(roi) == {'x', 'y', 'width', 'height'}
             and all(type(v) is int for v in roi.values()), 'invalid ROI')
        x, y, w, h = (roi[k] for k in ('x', 'y', 'width', 'height'))
        region = regions[tid]
        need(x >= 0 and y >= 0 and 8 <= w <= region['width']
             and 8 <= h <= region['height']
             and x + w <= region['width'] and y + h <= region['height'],
             'ROI outside table')
        frame = frames[key]
        need(all(proposal.get(k) == v for k, v in
                 (('table_id', tid), ('frame_file', name), ('field', field),
                  ('roi', roi), ('source_frame_sha256', frame['sha256']),
                  ('decoded_source_pts_seconds', frame['pts']),
                  ('frame_kind', frame['kind']),
                  ('roi_png', f'roi_{index:03d}.png'))),
             'OCR proposal/task/frame identity mismatch')
        need(sha_valid(proposal.get('roi_png_sha256'))
             and proposal.get('status') == 'needs_manual_review'
             and proposal.get('parsed_candidate') is None,
             'OCR proposal unexpectedly promoted')
        roi_file = ocr_dir / proposal['roi_png']
        need(roi_file.is_file() and not roi_file.is_symlink()
             and 8 <= roi_file.stat().st_size <= MAX_PNG_BYTES
             and digest(roi_file) == proposal['roi_png_sha256'],
             'ROI PNG missing or hash mismatch')
        if frame['kind'] == 'sparse':
            need(key in sparse, 'unknown sparse frame')
            source_record = sparse[key]
            requested = source_record['timestamp_seconds']
        else:
            need(key in dense_lookup, 'unknown dense frame')
            source_record = dense_lookup[key]
            requested = source_record['requested_seconds']
        need(pts_valid(requested) and requested >= 0, 'invalid requested timestamp')
        needed_frames[key] = (frame, requested, regions[tid])
        roi_plan.append((index, key, roi, roi_file, proposal['roi_png_sha256']))

    with tempfile.TemporaryDirectory(prefix='plo_ocr_source_replay_') as temp:
        root = Path(temp)
        reproduced = {}
        for n, (key, (frame, requested, region)) in enumerate(sorted(needed_frames.items())):
            output = root / f'frame_{n:03d}.jpg'
            crop = f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"
            result = extract_sample_frame(video, crop, requested, output,
                                          manifest['media']['frame_rate_reported'])
            need(abs(result['actual_frame_timestamp_seconds'] - frame['pts']) <= 1e-5,
                 'source frame replay PTS mismatch')
            need(digest(output) == frame['sha256'],
                 'source frame replay JPEG mismatch (possible FFmpeg version drift)')
            reproduced[key] = output
        for index, key, roi, roi_file, expected_sha in roi_plan:
            output = root / f'roi_{index:03d}.png'
            replay_roi(reproduced[key], roi, output)
            need(digest(output) == expected_sha,
                 'ROI PNG replay mismatch (possible FFmpeg version drift)')
        # Re-check all critical inputs after replay to reduce TOCTOU exposure.
        need(digest(video) == manifest['source_sha256']
             and digest(regions_json) == manifest['regions_config_sha256']
             and digest(tasks_json) == ocr['source_roi_tasks_sha256']
             and digest(ocr_path) == ocr_sha
             and all(digest(roi_file) == expected for _, _, _, roi_file, expected in roi_plan),
             'input changed during replay')
        evidence_index(ingest_dir, changes_json, refined_dir)
    return {
        'schema_version': 1,
        'analysis_status': 'offline_ocr_source_replay_evidence_only',
        'source_video_sha256': manifest['source_sha256'],
        'source_roi_ocr_report_sha256': ocr_sha,
        'source_frames_replayed_exactly': len(reproduced),
        'roi_pngs_replayed_exactly': len(roi_plan),
        'same_ffmpeg_build_replay_required': True,
        'source_video_to_frame_to_roi_reproduced': True,
        'hands_reconstructed': False,
        'ready_for_equity_or_ev': False,
        'ocr_semantics_verified': False,
        'warning': 'Exact media replay validates reproducibility in this toolchain, not OCR accuracy, hand identity or poker decisions.'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('video', 'regions_json', 'ingest_dir', 'changes_json',
                'refined_dir', 'tasks_json', 'ocr_dir'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.video, args.regions_json, args.ingest_dir,
                           args.changes_json, args.refined_dir, args.tasks_json,
                           args.ocr_dir), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
