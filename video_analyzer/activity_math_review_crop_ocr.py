"""Audited offline OCR probes on manual ROIs of math-review table stills.

Rebuilds both the FFmpeg PTS audit and the table crops from their original
sources before trusting their manifests. All OCR output is unverified text;
no poker state, mathematical result, or clip is authorized.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from activity_math_review_pts_audit import audit_math_review_pts
from activity_math_review_table_stills import export_math_review_table_stills
from ocr_candidates import FIELDS, candidate_from_ocr
from ocr_probe import parse_tesseract_tsv


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _regular(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('Expected regular non-symlink file')
    return p


def _load(path):
    return json.loads(_regular(path).read_text(encoding='utf-8'))


def _roi_config(config, regions):
    if (not isinstance(config, dict) or set(config) != {'schema_version', 'rois'}
            or type(config['schema_version']) is not int or config['schema_version'] != 1
            or not isinstance(config['rois'], list)
            or not 1 <= len(config['rois']) <= 16):
        raise ValueError('Expected 1..16 manual ROIs')
    dims = {r['table_id']: r for r in regions}
    rois = {}
    for row in config['rois']:
        if (not isinstance(row, dict)
                or set(row) != {'table_id', 'field', 'x', 'y', 'width', 'height'}
                or type(row['table_id']) is not int or row['table_id'] not in dims
                or row['field'] not in FIELDS
                or any(type(row[k]) is not int for k in ('x', 'y', 'width', 'height'))
                or min(row['x'], row['y']) < 0
                or min(row['width'], row['height']) < 1
                or row['x'] + row['width'] > dims[row['table_id']]['width']
                or row['y'] + row['height'] > dims[row['table_id']]['height']):
            raise ValueError('Invalid manual OCR region')
        key = (row['table_id'], row['field'])
        if key in rois:
            raise ValueError('Duplicate table/field OCR region')
        rois[key] = row
    return rois


def export_math_review_crop_ocr(video, frames_dir, handoff, triage, packet,
                                timeline, regions_json, table_dir, pts_dir,
                                rois_json, output_dir, *, max_tasks=64):
    """Publish hash-bound, unverified OCR candidates; no automatic poker inference."""
    if type(max_tasks) is not int or not 1 <= max_tasks <= 64:
        raise ValueError('Invalid OCR budget')
    paths = [_regular(x) for x in (video, handoff, triage, packet, timeline,
                                  regions_json, rois_json)]
    dirs = [Path(x) for x in (frames_dir, table_dir, pts_dir)]
    output = Path(output_dir)
    if (any(d.is_symlink() or not d.is_dir() for d in dirs)
            or output.exists() or output.is_symlink()
            or any(output.resolve().is_relative_to(d.resolve()) for d in dirs)):
        raise ValueError('Require existing non-symlink source dirs and new output outside them')
    table_manifest = _regular(dirs[1] / 'math_review_table_stills.json')
    pts_manifest = _regular(dirs[2] / 'math_review_pts_audit.json')
    sources = paths + [table_manifest, pts_manifest]
    initial_hashes = {str(p.resolve()): _sha(p) for p in sources}
    rois_config = _load(rois_json)
    supplied_table, supplied_pts = _load(table_manifest), _load(pts_manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_crop_ocr_', dir=output.parent) as tmp:
        stage = Path(tmp)
        # Re-run provenance checks instead of accepting an internally consistent,
        # but forged, JSON report or a crop whose digest was simply rewritten.
        fresh_pts = audit_math_review_pts(video, frames_dir, handoff, triage,
                                          packet, timeline, stage / 'rechecked_pts')
        fresh_table = export_math_review_table_stills(video, frames_dir, handoff,
            triage, packet, timeline, regions_json, stage / 'rechecked_tables')
        if supplied_pts != fresh_pts or supplied_table != fresh_table:
            raise ValueError('Upstream PTS or crop report differs from regenerated evidence')
        audit_by_frame = {r['filename']: r for r in fresh_pts['frames']}
        if len(audit_by_frame) != len(fresh_pts['frames']):
            raise ValueError('Duplicate frame PTS audit')
        rois = _roi_config(rois_config, fresh_table['regions'])
        crops = fresh_table['crops']
        if len(crops) * len(rois) > 256:
            raise ValueError('Excessive crop count')
        jobs = [(crop, roi) for crop in crops
                for (table, _), roi in sorted(rois.items()) if table == crop['table_id']]
        if len(jobs) > max_tasks:
            raise ValueError('OCR budget exceeded before processing')
        candidates = []
        for index, (crop, roi) in enumerate(jobs):
            crop_path = _regular(dirs[1] / crop['filename'])
            reference_path = _regular(stage / 'rechecked_tables' / crop['filename'])
            if (_sha(crop_path) != crop['sha256']
                    or _sha(reference_path) != crop['sha256']):
                raise ValueError('Crop pixels differ from regenerated crop')
            frame = audit_by_frame.get(crop['source_frame_filename'])
            if (frame is None or frame['source_png_sha256'] != crop['source_frame_sha256']
                    or frame['requested_seek_pts_seconds'] != crop['requested_seek_pts_seconds']):
                raise ValueError('Crop and PTS source frames do not agree')
            roi_path = stage / f'roi_{index:04d}.png'
            filter_str = f"crop={roi['width']}:{roi['height']}:{roi['x']}:{roi['y']}"
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-i', str(crop_path), '-vf', filter_str,
                            '-frames:v', '1', '-update', '1', '-y', str(roi_path)],
                           check=True, capture_output=True, timeout=40)
            proc = subprocess.run(['tesseract', str(roi_path), 'stdout',
                                   '--psm', '6', 'tsv'],
                                  check=True, capture_output=True, text=True, timeout=40)
            raw, words, confidence = parse_tesseract_tsv(proc.stdout)
            candidate = candidate_from_ocr({
                'table_id': crop['table_id'],
                'timestamp': crop['requested_seek_pts_seconds'],
                'text': raw, 'mean_engine_confidence': confidence},
                field=roi['field'])
            candidate.update({
                'source_crop_filename': crop['filename'],
                'source_crop_sha256': crop['sha256'],
                'roi_sha256': _sha(roi_path),
                'roi_coordinates_in_table_crop': {k: roi[k] for k in ('x', 'y', 'width', 'height')},
                'word_count': words,
                'requested_seek_pts_seconds': crop['requested_seek_pts_seconds'],
                'decoded_frame_pts_seconds': frame['decoded_frame_pts_seconds'],
                'decoded_pts_verified_by_identical_png': frame['png_bytes_match'],
                'timestamp_semantics': 'requested_seek_not_hand_boundary; decoded_filtergraph_pts_if_verified',
                'hand_ids_human_assigned_not_verified': sorted({
                    t['hand_id_human_assigned_not_verified']
                    for t in fresh_table['review_tasks']
                    if t['table_id'] == crop['table_id']
                    and t['crop_filename'] == crop['filename']}),
                'poker_event_verified': False, 'requires_manual_review': True})
            candidates.append(candidate)
        # Recheck every input after external processes complete.
        if any(_sha(p) != initial_hashes[str(p.resolve())] for p in sources):
            raise ValueError('Source changed during OCR')
        if any(_sha(_regular(dirs[1] / c['filename'])) != c['sha256'] for c in crops):
            raise ValueError('Source crop changed during OCR')
        report = {
            'schema_version': 1,
            'analysis_status': 'unverified_manual_roi_ocr_on_audited_navigation_crops',
            'recording_sha256': fresh_table['recording_sha256'],
            'source_table_manifest_sha256': initial_hashes[str(table_manifest.resolve())],
            'source_pts_audit_sha256': initial_hashes[str(pts_manifest.resolve())],
            'source_roi_config_sha256': initial_hashes[str(paths[-1].resolve())],
            'candidates': candidates,
            'counts': {'ocr_probes': len(candidates),
                       'with_verified_decoded_pts': sum(c['decoded_pts_verified_by_identical_png'] for c in candidates),
                       'needs_manual_review': len(candidates)},
            'requires_manual_review': True, 'cards_or_actions_verified': False,
            'ready_for_equity_or_ev': False, 'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': 'Manual ROI and OCR guesses are unverified; decoded PTS is filtergraph time, not capture time or a hand boundary.'}
        (stage / 'math_review_crop_ocr.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '
', encoding='utf-8')
        # The stage also contains recheck data; publish only the report.
        final = stage / 'publish'
        final.mkdir()
        os.replace(stage / 'math_review_crop_ocr.json', final / 'math_review_crop_ocr.json')
        os.replace(final, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'frames_dir', 'handoff', 'triage', 'packet', 'timeline',
                 'regions_json', 'table_dir', 'pts_dir', 'rois_json', 'output_dir'):
        parser.add_argument(name)
    parser.add_argument('--max-tasks', type=int, default=64)
    args = parser.parse_args(argv)
    result = export_math_review_crop_ocr(
        *(getattr(args, name) for name in ('video', 'frames_dir', 'handoff', 'triage',
        'packet', 'timeline', 'regions_json', 'table_dir', 'pts_dir', 'rois_json', 'output_dir')),
        max_tasks=args.max_tasks)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
