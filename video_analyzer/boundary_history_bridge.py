"""Offline, evidence-linked navigation spans; NEVER reconstructed poker hands.

Only two independently PTS-byte-matched, human-reported transitions can bound a
navigation span. Other OCR candidate windows are retained rather than silently
omitted. All output remains unsuitable for equity, EV or automated clips.
"""
import hashlib
import json
import math
from pathlib import Path

FALSE = ('hand_boundaries_verified', 'cards_or_actions_verified',
         'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
         'strategic_error_established')
VERDICTS = ('confirmed_transition', 'rejected_transition', 'uncertain')
MAX_TASKS = 2048


def _seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _frame_provenance(frame):
    """Keep supplied audit metadata; never manufacture a verified observation."""
    return {'frame_id': frame['frame_id'],
            'pts_byte_matched': frame['pts_byte_matched'] is True,
            'png_sha256': frame.get('png_sha256'),
            'requested_seek_seconds': frame.get('requested_seek_seconds'),
            'decoded_pts_seconds': frame.get('decoded_pts_seconds')}


def _read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'),
                      object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError('Non-finite JSON number: ' + value)))


def build(packet, labels, packet_sha):
    if (not isinstance(packet, dict) or not isinstance(labels, dict)
            or packet.get('schema_version') != 1 or labels.get('schema_version') != 1
            or packet.get('analysis_status') != 'candidate_boundary_review_only'
            or labels.get('analysis_status') != 'unverified_human_boundary_labels'
            or not isinstance(packet_sha, str) or labels.get('packet_sha256') != packet_sha
            or any(packet.get(k) is not False or labels.get(k) is not False for k in FALSE)):
        raise ValueError('Untrusted source')
    recording_sha = packet.get('recording_sha256')
    if (not isinstance(recording_sha, str) or len(recording_sha) != 64
            or any(c not in '0123456789abcdef' for c in recording_sha)):
        raise ValueError('Invalid recording digest')
    tasks = packet.get('tasks')
    annotations = labels.get('annotations')
    if (not isinstance(tasks, list) or not isinstance(annotations, list)
            or len(tasks) > MAX_TASKS or len(annotations) > len(tasks)):
        raise ValueError('Invalid task/annotation budget')
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('Invalid task')
        tid, table = task.get('task_id'), task.get('table_id')
        start, end = task.get('window_start_seconds'), task.get('window_end_seconds')
        frames = task.get('frames')
        if (not isinstance(tid, str) or not tid or len(tid) > 200 or tid in by_id
                or type(table) is not int or not 1 <= table <= 4
                or not _seconds(start) or not _seconds(end) or start > end
                or not isinstance(frames, list) or len(frames) > 120):
            raise ValueError('Invalid or duplicate task')
        frame_map = {}
        for frame in frames:
            if not isinstance(frame, dict):
                raise ValueError('Invalid frame')
            fid = frame.get('frame_id')
            if (type(fid) is not int or fid < 0 or fid in frame_map
                    or type(frame.get('pts_byte_matched')) is not bool):
                raise ValueError('Invalid or duplicate frame')
            frame_map[fid] = frame
        by_id[tid] = (task, frame_map)
    annotations_by_id = {}
    confirmed = {i: [] for i in range(1, 5)}
    for row in annotations:
        if not isinstance(row, dict):
            raise ValueError('Invalid annotation')
        tid, verdict = row.get('task_id'), row.get('verdict_reported_by_human')
        if (not isinstance(tid, str) or tid not in by_id or tid in annotations_by_id
                or verdict not in VERDICTS
                or row.get('independently_verified') is not False):
            raise ValueError('Invalid or duplicate annotation')
        task, frame_map = by_id[tid]
        refs = row.get('frame_ids')
        ts = row.get('timestamp_reported_by_human')
        if (not isinstance(refs, list) or len(refs) != len(set(map(str, refs)))
                or any(type(fid) is not int or fid not in frame_map for fid in refs)):
            raise ValueError('Invalid frame references')
        if verdict == 'confirmed_transition':
            if (not _seconds(ts)
                    or not task['window_start_seconds'] <= ts <= task['window_end_seconds']
                    or not refs or any(frame_map[fid]['pts_byte_matched'] is not True
                                       for fid in refs)):
                raise ValueError('Unverifiable transition')
            confirmed[task['table_id']].append((ts, tid, task))
        elif ts is not None:
            raise ValueError('Unconfirmed transition cannot assert timestamp')
        annotations_by_id[tid] = row
    if 'pending' in labels and (type(labels['pending']) is not int
                                or labels['pending'] != len(tasks) - len(annotations)):
        raise ValueError('Incorrect pending count')

    spans = []
    for table, points in confirmed.items():
        points.sort(key=lambda p: (p[0], p[1]))
        for i, (a, b) in enumerate(zip(points, points[1:])):
            if a[0] >= b[0] or a[2]['window_end_seconds'] >= b[2]['window_start_seconds']:
                raise ValueError('Conflicting transitions')
            interior = []
            for tid, (task, frames) in by_id.items():
                if (task['table_id'] != table or tid in (a[1], b[1])
                        or task['window_start_seconds'] >= b[0]
                        or task['window_end_seconds'] <= a[0]):
                    continue
                label = annotations_by_id.get(tid)
                verdict = label['verdict_reported_by_human'] if label else 'pending'
                # A confirmed interior point would be an adjacent boundary instead.
                if verdict == 'confirmed_transition':
                    raise ValueError('Non-adjacent confirmed boundary')
                refs = label['frame_ids'] if label else []
                interior.append({
                    'task_id': tid, 'review_status': verdict,
                    'window_start_seconds': task['window_start_seconds'],
                    'window_end_seconds': task['window_end_seconds'],
                    'reviewed_frame_provenance': [_frame_provenance(frames[fid]) for fid in refs],
                    'could_hide_additional_transition': verdict in ('pending', 'uncertain')})
            interior.sort(key=lambda c: (c['window_start_seconds'], c['task_id']))
            endpoints = []
            for ts, tid, task in (a, b):
                label = annotations_by_id[tid]
                frames = by_id[tid][1]
                endpoints.append({
                    'task_id': tid, 'timestamp_reported_by_human': ts,
                    'frame_provenance': [_frame_provenance(frames[fid])
                                         for fid in label['frame_ids']],
                    'independently_verified': False})
            spans.append({
                'table_id': table, 'span_index': i,
                'start_human_seconds': a[0], 'end_human_seconds': b[0],
                'source_task_ids': [a[1], b[1]],
                'boundary_evidence': endpoints,
                'interior_candidates': interior,
                'contains_unresolved_interior_candidates': any(
                    c['could_hide_additional_transition'] for c in interior),
                'hand_id': None, 'cards': None, 'actions': [],
                'equity': None, 'ev': None, 'requires_manual_review': True})
    spans.sort(key=lambda s: (s['table_id'], s['start_human_seconds']))
    return {'schema_version': 2, 'analysis_status': 'navigation_only_unverified_spans',
            'recording_sha256': recording_sha,
            'source_packet_sha256': packet_sha, 'candidate_spans': spans,
            'counts': {'tasks': len(tasks), 'annotations': len(annotations),
                       'pending': len(tasks) - len(annotations),
                       'spans': len(spans),
                       'spans_with_unresolved_interior_candidates': sum(
                           s['contains_unresolved_interior_candidates'] for s in spans)},
            'requires_manual_review': True,
            **{k: False for k in FALSE}}


def export(packet_file, labels_file, output_file):
    out = Path(output_file)
    if out.exists() or out.is_symlink():
        raise ValueError('Output exists')
    p, l = Path(packet_file), Path(labels_file)
    if (p.is_symlink() or l.is_symlink() or not p.is_file() or not l.is_file()
            or out.resolve() in (p.resolve(), l.resolve())):
        raise ValueError('Unsafe input/output path')
    raw = p.read_bytes()
    packet, labels = _read_json(p), _read_json(l)
    result = build(packet, labels, hashlib.sha256(raw).hexdigest())
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    return result
