"""Offline OCR for activity-selected, decoded-PTS table crops.

The activity evidence schema differs from the regular-interval evidence schema.
This adapter audits its own hash-bound manifest, deduplicates requested seeks
mapping to one decoded frame, and preserves PTS provenance. OCR is never truth.
No live capture, betting, inferred actions, hand boundaries, equity, or EV.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from activity_evidence_export import audit_activity_evidence
from activity_frame_index import index_activity_frames
from evidence_ocr import _roi
from ocr_candidates import FIELDS, candidate_from_ocr
from ocr_probe import parse_tesseract_tsv
from video_segments import _run


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def prepare_activity_ocr_jobs(evidence_dir, roi_manifest, *, max_tasks=2400):
    """Audit all evidence and create one OCR task per unique frame and ROI.

    This function performs no OCR. The ROI manifest must be supplied manually.
    No approximate timestamp joins are performed: duplicates must match exactly.
    """
    if type(max_tasks) is not int or not 1 <= max_tasks <= 2400:
        raise ValueError('max_tasks must be an integer in [1, 2400]')
    root = Path(evidence_dir).resolve(strict=True)
    manifest_file = root / 'manifest.json'
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ValueError('Unsafe or missing evidence manifest')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    audit = audit_activity_evidence(manifest, root)
    if not audit['ok']:
        raise ValueError('Activity evidence audit failed')
    if isinstance(roi_manifest, (str, Path)):
        roi_manifest = json.loads(Path(roi_manifest).read_text(encoding='utf-8'))
    roi_rows = roi_manifest.get('tasks') if isinstance(roi_manifest, dict) else None
    if not isinstance(roi_rows, list) or not 1 <= len(roi_rows) <= 16:
        raise ValueError('Expected 1..16 manually defined table/field ROIs')
    tables = {}
    for region in manifest['regions']:
        table = region.get('table_id')
        if (type(table) is not int or table not in (1, 2, 3, 4)
                or table in tables):
            raise ValueError('Invalid or repeated table region')
        tables[table] = region
    rois = {}
    for row in roi_rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid ROI task')
        table, field = row.get('table_id'), row.get('field')
        if type(table) is not int or table not in tables or field not in FIELDS:
            raise ValueError('Invalid ROI table or field')
        key = (table, field)
        if key in rois:
            raise ValueError('Duplicate ROI for table/field')
        region = tables[table]
        crop = _roi(row.get('region'), region['width'], region['height'])
        rois[key] = crop
    unique = index_activity_frames(manifest)
    jobs = []
    for frame in unique:
        for (table, field), crop in sorted(rois.items()):
            if table != frame['table_id']:
                continue
            jobs.append({**frame,
                         'field': field, 'crop_filter': crop})
    if len(jobs) > max_tasks:
        raise ValueError('Activity OCR task limit exceeded before execution')
    return {'schema_version': 1, 'analysis_status': 'unverified_activity_ocr_jobs_only',
            'requires_manual_review': True,
            'timestamp_semantics': 'decoded_filtergraph_pts_not_capture_time',
            'evidence_manifest_sha256': _hash(manifest_file),
            'recording_sha256': manifest['recording_sha256'],
            'requested_seeks': manifest['requested_count'],
            'unique_table_frames': len(unique), 'ocr_jobs': len(jobs),
            'unresolved_seeks': len(manifest['unresolved']),
            'jobs': jobs,
            'warning': 'OCR is unverified. Decoded PTS do not authenticate capture time or poker actions.'}


def scan_activity_ocr(evidence_dir, roi_manifest, output_json, *, max_tasks=2400,
                      min_engine_confidence=.75):
    """OCR each unique activity-selected table frame; never overwrite reports."""
    output = Path(output_json)
    if output.exists():
        raise FileExistsError('OCR output already exists')
    root = Path(evidence_dir).resolve(strict=True)
    plan = prepare_activity_ocr_jobs(root, roi_manifest, max_tasks=max_tasks)
    candidates = []
    with tempfile.TemporaryDirectory(prefix='plo_activity_ocr_') as scratch:
        cropped = Path(scratch) / 'crop.png'
        for job in plan['jobs']:
            source = root / job['source_image']
            # Recheck each file immediately before OCR, not only during planning.
            if source.is_symlink() or not source.is_file() or _hash(source) != job['source_sha256']:
                raise ValueError('Evidence changed before OCR')
            _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                  '-i', str(source), '-vf', job['crop_filter'], '-frames:v', '1', str(cropped)])
            proc = subprocess.run(['tesseract', str(cropped), 'stdout', '--psm', '6', 'tsv'],
                                  check=True, capture_output=True, text=True, timeout=30)
            raw, _, confidence = parse_tesseract_tsv(proc.stdout)
            candidate = candidate_from_ocr({
                'table_id': job['table_id'], 'timestamp': job['timestamp'],
                'text': raw, 'mean_engine_confidence': confidence,
            }, field=job['field'], min_engine_confidence=min_engine_confidence)
            candidate.update({
                'source_image': job['source_image'],
                'source_sha256': job['source_sha256'],
                'source_pts_ticks': job['source_pts_ticks'],
                'requested_seeks': job['requested_seeks'],
                'seek_reasons': job['seek_reasons'],
                'timestamp_semantics': plan['timestamp_semantics'],
                'evidence_manifest_sha256': plan['evidence_manifest_sha256'],
            })
            candidates.append(candidate)
    report = {'schema_version': 1, 'analysis_status': 'unverified_ocr_candidates_only',
              'requires_manual_review': True,
              'timestamp_semantics': plan['timestamp_semantics'],
              'evidence_manifest_sha256': plan['evidence_manifest_sha256'],
              'recording_sha256': plan['recording_sha256'],
              'requested_seeks': plan['requested_seeks'],
              'unique_table_frames': plan['unique_table_frames'],
              'unresolved_seeks': plan['unresolved_seeks'],
              'candidates': candidates,
              'ready_for_equity_or_ev': False,
              'warning': ('All OCR fields are unverified, confidence is not calibrated. '
                          'Missing frames or hidden cards are never reconstructed as facts.')}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence_dir')
    parser.add_argument('manual_rois_json')
    parser.add_argument('output_json')
    parser.add_argument('--max-tasks', type=int, default=2400)
    args = parser.parse_args()
    result = scan_activity_ocr(args.evidence_dir, args.manual_rois_json,
                               args.output_json, max_tasks=args.max_tasks)
    print(json.dumps({'ocr_candidates_unverified': len(result['candidates']),
                      'unresolved_seeks': result['unresolved_seeks']}))
