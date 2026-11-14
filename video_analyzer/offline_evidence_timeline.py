"""Conservative timeline for crop-frame evidence; never asserts original-video identity."""
import json
import math
from pathlib import Path


def build_timeline(evidence, *, crop_start_seconds=None):
    if not isinstance(evidence, dict) or evidence.get('status') != 'TECHNICAL_FRAME_EVIDENCE_ONLY':
        raise ValueError('unreviewed technical evidence required')
    for key in ('source_absolute_pts_verified', 'ocr_verified', 'hands_verified', 'equity_ev_verified'):
        if evidence.get(key) is not False:
            raise ValueError('verification claim prohibited')
    tables = evidence.get('tables')
    if not isinstance(tables, list) or not 1 <= len(tables) <= 4:
        raise ValueError('expected 1-4 tables')
    if crop_start_seconds is not None and (type(crop_start_seconds) not in (int, float)
        or not math.isfinite(crop_start_seconds) or crop_start_seconds < 0):
        raise ValueError('invalid crop start')
    events, ids = [], set()
    for table in tables:
        if not isinstance(table, dict) or table.get('status') != 'UNREVIEWED_FRAME_EVIDENCE':
            raise ValueError('unreviewed table required')
        tid, count, samples = table.get('table_id'), table.get('decoded_frame_count'), table.get('samples')
        if type(tid) is not int or tid not in range(1, 5) or tid in ids:
            raise ValueError('invalid table ID')
        ids.add(tid)
        if type(count) is not int or count < 1 or not isinstance(samples, list) or not samples:
            raise ValueError('invalid frames')
        previous_index, previous_pts = -1, -1.0
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError('invalid sample')
            index, pts, digest = sample.get('frame_index'), sample.get('crop_pts_seconds'), sample.get('rgb_sha256')
            if type(index) is not int or not previous_index < index < count:
                raise ValueError('unordered frame index')
            if type(pts) not in (int, float) or not math.isfinite(pts) or pts < 0 or pts <= previous_pts:
                raise ValueError('unordered crop PTS')
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('invalid SHA256')
            event = {'table_id': tid, 'frame_index': index, 'crop_pts_seconds': pts,
                     'rgb_sha256': digest, 'review_status': 'UNREVIEWED'}
            if crop_start_seconds is not None:
                event['nominal_source_seconds'] = round(crop_start_seconds + pts, 6)
                event['nominal_source_seconds_verified'] = False
            events.append(event)
            previous_index, previous_pts = index, pts
    events.sort(key=lambda e: (e['crop_pts_seconds'], e['table_id'], e['frame_index']))
    return {'status': 'UNREVIEWED_TIMELINE', 'events': events,
            'absolute_source_pts_verified': False, 'hand_boundaries_verified': False,
            'ocr_verified': False, 'equity_ev_verified': False}


def write_timeline(evidence_path, output_path, *, crop_start_seconds=None):
    src, dst = Path(evidence_path), Path(output_path)
    if src.is_symlink() or not src.is_file() or dst.is_symlink() or src.resolve() == dst.resolve():
        raise ValueError('unsafe path')
    result = build_timeline(json.loads(src.read_text(encoding='utf-8')),
                            crop_start_seconds=crop_start_seconds)
    if dst.exists():
        raise FileExistsError('refusing overwrite')
    with dst.open('x', encoding='utf-8') as file:
        json.dump(result, file, indent=2, ensure_ascii=False)
    return result
