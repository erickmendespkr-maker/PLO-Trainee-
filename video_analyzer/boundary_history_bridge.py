"""Offline navigation spans from human OCR-boundary labels; NOT reconstructed hands."""
import hashlib
import json
import math
from pathlib import Path

FALSE = ('hand_boundaries_verified', 'cards_or_actions_verified',
         'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
         'strategic_error_established')


def build(packet, labels, packet_sha):
    if (packet.get('analysis_status') != 'candidate_boundary_review_only'
            or labels.get('analysis_status') != 'unverified_human_boundary_labels'
            or labels.get('packet_sha256') != packet_sha
            or any(packet.get(k) is not False or labels.get(k) is not False for k in FALSE)):
        raise ValueError('Untrusted source')
    tasks = packet['tasks']
    by_id = {t['task_id']: t for t in tasks}
    if len(tasks) > 2048 or len(by_id) != len(tasks):
        raise ValueError('Duplicate/excess tasks')
    confirmed = {i: [] for i in range(1, 5)}
    seen = set()
    for row in labels['annotations']:
        tid = row['task_id']
        if tid not in by_id or tid in seen or row.get('independently_verified') is not False:
            raise ValueError('Invalid label')
        seen.add(tid)
        if row['verdict_reported_by_human'] != 'confirmed_transition':
            continue
        task = by_id[tid]
        table, ts = task['table_id'], row['timestamp_reported_by_human']
        frames = {f['frame_id']: f for f in task['frames']}
        refs = row['frame_ids']
        if (type(table) is not int or table not in confirmed
                or type(ts) not in (int, float) or not math.isfinite(ts)
                or not task['window_start_seconds'] <= ts <= task['window_end_seconds']
                or not refs or any(type(i) is not int or i not in frames
                                    or frames[i].get('pts_byte_matched') is not True for i in refs)):
            raise ValueError('Unverifiable transition')
        confirmed[table].append((ts, tid, task['window_start_seconds'], task['window_end_seconds']))
    spans = []
    for table, points in confirmed.items():
        points.sort()
        for i, (a, b) in enumerate(zip(points, points[1:])):
            if a[0] >= b[0] or a[3] >= b[2]:
                raise ValueError('Conflicting transitions')
            spans.append({'table_id': table, 'span_index': i,
                          'start_human_seconds': a[0], 'end_human_seconds': b[0],
                          'source_task_ids': [a[1], b[1]],
                          'hand_id': None, 'cards': None, 'actions': [],
                          'equity': None, 'ev': None, 'requires_manual_review': True})
    return {'schema_version': 1, 'analysis_status': 'navigation_only_unverified_spans',
            'recording_sha256': packet['recording_sha256'],
            'source_packet_sha256': packet_sha, 'candidate_spans': spans,
            **{k: False for k in FALSE}}


def export(packet_file, labels_file, output_file):
    out = Path(output_file)
    if out.exists() or out.is_symlink():
        raise ValueError('Output exists')
    p, l = Path(packet_file), Path(labels_file)
    if p.is_symlink() or l.is_symlink():
        raise ValueError('Symlink input')
    raw = p.read_bytes()
    packet, labels = json.loads(raw), json.loads(l.read_text(encoding='utf-8'))
    result = build(packet, labels, hashlib.sha256(raw).hexdigest())
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
    return result
