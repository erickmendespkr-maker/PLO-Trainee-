"""Unverified OCR from pre-extracted video evidence and manual per-table ROIs."""
import json
import math
from pathlib import Path
import subprocess
import tempfile

from ocr_candidates import FIELDS, candidate_from_ocr
from ocr_probe import parse_tesseract_tsv
from video_segments import _run

def _roi(value, width, height):
    if not isinstance(value, dict) or set(value) != {'x', 'y', 'width', 'height'}:
        raise ValueError('ROI must contain x,y,width,height')
    if any(isinstance(value[k], bool) or not isinstance(value[k], int) for k in value):
        raise ValueError('ROI coordinates must be integers')
    x, y, w, h = (value[k] for k in ('x', 'y', 'width', 'height'))
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError('ROI outside table image')
    return f'crop={w}:{h}:{x}:{y}'

def scan_evidence(evidence_dir, roi_manifest, output_json, *, max_tasks=4000):
    if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or max_tasks < 1:
        raise ValueError('max_tasks must be positive')
    output_json = Path(output_json)
    if output_json.exists():
        raise FileExistsError('Output JSON already exists')
    evidence_dir = Path(evidence_dir).resolve()
    report = json.loads((evidence_dir / 'manifest.json').read_text(encoding='utf-8'))
    if report.get('analysis_status') != 'unverified_visual_evidence_only':
        raise ValueError('Expected unverified evidence manifest')
    roi_data = json.loads(Path(roi_manifest).read_text(encoding='utf-8'))
    tasks = roi_data.get('tasks') if isinstance(roi_data, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 16:
        raise ValueError('Expected 1..16 manual ROIs')
    regions = {r['table_id']: r for r in report['regions']}
    selected = {}
    for task in tasks:
        if not isinstance(task, dict) or task.get('field') not in FIELDS:
            raise ValueError('Invalid ROI task')
        table_id = task.get('table_id')
        if isinstance(table_id, bool) or not isinstance(table_id, int) or table_id not in regions:
            raise ValueError('Unknown table ID')
        table = regions[table_id]
        crop = _roi(task.get('region'), table['width'], table['height'])
        key = (table_id, task['field'])
        if key in selected:
            raise ValueError('Duplicate table/field ROI')
        selected[key] = crop
    jobs = [(frame, field, crop) for frame in report['frames']
            for (table_id, field), crop in selected.items() if table_id == frame['table_id']]
    if len(jobs) > max_tasks:
        raise ValueError('OCR task limit exceeded')
    candidates = []
    with tempfile.TemporaryDirectory(prefix='plo_evidence_ocr_') as tmp:
        temp_image = Path(tmp) / 'roi.png'
        for frame, field, crop in jobs:
            if frame.get('status') != 'unverified_visual_evidence':
                raise ValueError('Expected unverified frame')
            relative = frame.get('image')
            if not isinstance(relative, str):
                raise ValueError('Invalid frame filename')
            image = (evidence_dir / relative).resolve()
            if not image.is_relative_to(evidence_dir) or not image.is_file() or image.suffix.lower() != '.png':
                raise ValueError('Frame must be a PNG inside evidence directory')
            timestamp = frame['nominal_timestamp_seconds']
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError('Invalid frame timestamp')
            _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                  '-i', str(image), '-vf', crop, '-frames:v', '1', str(temp_image)])
            ocr = subprocess.run(['tesseract', str(temp_image), 'stdout', '--psm', '6', 'tsv'],
                                 check=True, capture_output=True, text=True, timeout=30)
            raw, count, confidence = parse_tesseract_tsv(ocr.stdout)
            candidate = candidate_from_ocr({'table_id': frame['table_id'],
                'timestamp': float(timestamp), 'text': raw,
                'mean_engine_confidence': confidence}, field=field)
            candidate['source_image'] = relative
            candidate['timestamp_semantics'] = 'nominal_sampling_grid_not_exact_source_pts'
            candidates.append(candidate)
    result = {'schema_version': 1, 'analysis_status': 'unverified_ocr_candidates_only',
              'requires_manual_review': True, 'candidates': candidates,
              'warning': 'Unverified OCR; nominal frame times; no direct EV or action reconstruction.'}
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result
