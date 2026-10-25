"""Evidence-bound, offline human-review packet for OCR hand-transition hints."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile

from activity_ocr_boundary_pts_audit import audit_ocr_boundary_pts

FALSE = ('hand_boundaries_verified', 'cards_or_actions_verified',
         'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
         'strategic_error_established')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('Expected regular input file')
    return json.loads(p.read_text(encoding='utf-8'))


def write_new(path, obj):
    p = Path(path)
    if p.exists() or p.is_symlink():
        raise ValueError('Output already exists')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def packet(video, temporal, boundary, evidence, audit, output, regions=None):
    """Repeat bounded FFmpeg PTS audit; never trust an editable audit blindly."""
    sources = [Path(p) for p in (video, temporal, boundary, audit)]
    if regions is not None:
        sources.append(Path(regions))
    destination = Path(output)
    evidence = Path(evidence)
    if (any(p.is_symlink() or not p.is_file() for p in sources)
            or evidence.is_symlink() or not evidence.is_dir()
            or destination.resolve() in {p.resolve() for p in sources}
            or destination.resolve().is_relative_to(evidence.resolve())):
        raise ValueError('Unsafe input/output path')
    hashes = [digest(p) for p in sources]
    with tempfile.TemporaryDirectory(prefix='plo_boundary_handoff_') as temp:
        checked = audit_ocr_boundary_pts(video, temporal, boundary, evidence,
                   Path(temp) / 'rechecked', regions_json=regions)
    if load(audit) != checked:
        raise ValueError('Supplied PTS audit differs from independent re-decode')
    manifest = load(evidence / 'boundary_visual_evidence.json')
    windows = load(boundary)['review_windows']
    if len(windows) > 2048 or len(manifest['frames']) > 120:
        raise ValueError('Review budget exceeded')
    frames = {f['frame_id']: f for f in manifest['frames']}
    pts = {f['frame_id']: f for f in checked['frames']}
    if len(frames) != len(manifest['frames']) or len(pts) != len(frames):
        raise ValueError('Duplicate frame IDs')
    links = {}
    for link in manifest['window_associations']:
        idx = link['window_index']
        if type(idx) is not int or not 0 <= idx < len(windows) or idx in links:
            raise ValueError('Invalid window association')
        links[idx] = link['frame_ids']
    tasks = []
    for i, w in enumerate(windows):
        refs = []
        for fid in links.get(i, []):
            frame, check = frames[fid], pts[fid]
            if frame['table_id'] != w['table_id']:
                raise ValueError('Cross-table evidence')
            refs.append({'frame_id': fid, 'filename': frame['filename'],
                         'png_sha256': frame['sha256'],
                         'requested_seek_seconds': frame['requested_seek_seconds'],
                         'decoded_pts_seconds': check['decoded_pts_seconds'],
                         'pts_byte_matched': check['png_bytes_match']})
        tasks.append({'task_id': f"table_{w['table_id']:02d}_window_{i:04d}",
                      'table_id': w['table_id'],
                      'window_start_seconds': w['review_window_start_seconds'],
                      'window_end_seconds': w['review_window_end_seconds'],
                      'priority': w['priority'], 'signals': [s['kind'] for s in w['signals']],
                      'ambiguity_flags': w['ambiguity_flags'], 'frames': refs,
                      'status': 'pending_human_review'})
    if any(digest(p) != h for p, h in zip(sources, hashes)):
        raise ValueError('Input changed during processing')
    result = {'schema_version': 1, 'analysis_status': 'candidate_boundary_review_only',
              'recording_sha256': checked['recording_sha256'],
              'boundary_sha256': digest(boundary), 'audit_sha256': digest(audit),
              'tasks': tasks, 'requires_manual_review': True,
              **{key: False for key in FALSE},
              'counts': {'tasks': len(tasks), 'with_frames': sum(bool(t['frames']) for t in tasks)},
              'warning': 'Navigation and human review only; no verified hand, equity, EV, or clip authorization.'}
    write_new(output, result)
    return result


def template(packet_path, output):
    p = load(packet_path)
    if p.get('analysis_status') != 'candidate_boundary_review_only':
        raise ValueError('Invalid packet')
    result = {'schema_version': 1, 'packet_sha256': digest(packet_path),
              'annotations': [{'task_id': t['task_id'], 'verdict': None,
                               'reviewer': '', 'timestamp_seconds': None,
                               'frame_ids': [], 'notes': ''} for t in p['tasks']]}
    write_new(output, result)
    return result


def annotate(packet_path, annotations_path, output):
    p, a = load(packet_path), load(annotations_path)
    if (p.get('analysis_status') != 'candidate_boundary_review_only'
            or a.get('packet_sha256') != digest(packet_path)
            or a.get('schema_version') != 1
            or not isinstance(a.get('annotations'), list)):
        raise ValueError('Invalid annotation provenance')
    tasks = {t['task_id']: t for t in p['tasks']}
    if len(tasks) != len(p['tasks']):
        raise ValueError('Duplicate task IDs')
    seen, rows = set(), []
    for item in a['annotations']:
        if not isinstance(item, dict) or set(item) != {
                'task_id', 'verdict', 'reviewer', 'timestamp_seconds', 'frame_ids', 'notes'}:
            raise ValueError('Invalid annotation fields')
        tid, verdict = item['task_id'], item['verdict']
        if (not isinstance(tid, str) or tid not in tasks or tid in seen
                or verdict not in ('confirmed_transition', 'rejected_transition', 'uncertain')):
            raise ValueError('Invalid task/verdict')
        seen.add(tid)
        task, ids, ts = tasks[tid], item['frame_ids'], item['timestamp_seconds']
        if (not isinstance(item['reviewer'], str) or not 1 <= len(item['reviewer'].strip()) <= 80
                or not isinstance(item['notes'], str) or len(item['notes']) > 1000
                or not isinstance(ids, list) or any(type(x) is not int for x in ids)
                or len(ids) != len(set(ids))
                or not set(ids).issubset({f['frame_id'] for f in task['frames']})):
            raise ValueError('Invalid reviewer evidence')
        if verdict == 'confirmed_transition':
            if (type(ts) not in (int, float) or not math.isfinite(ts)
                    or not task['window_start_seconds'] <= ts <= task['window_end_seconds']
                    or not ids):
                raise ValueError('Confirmation requires in-window timestamp and evidence')
        elif ts is not None:
            raise ValueError('Unconfirmed transition cannot assert timestamp')
        rows.append({'task_id': tid, 'verdict_reported_by_human': verdict,
                     'timestamp_reported_by_human': ts,
                     'reviewer': item['reviewer'].strip(), 'notes': item['notes'],
                     'frame_ids': ids, 'independently_verified': False})
    result = {'schema_version': 1, 'analysis_status': 'unverified_human_boundary_labels',
              'packet_sha256': digest(packet_path), 'annotations': rows,
              'pending': len(tasks) - len(rows), 'requires_manual_review': True,
              **{key: False for key in FALSE}}
    write_new(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('packet')
    for arg in ('video', 'temporal', 'boundary', 'evidence', 'audit', 'output'):
        p.add_argument(arg)
    p.add_argument('--regions')
    for mode in ('template', 'annotate'):
        q = sub.add_parser(mode)
        q.add_argument('packet')
        if mode == 'annotate':
            q.add_argument('annotations')
        q.add_argument('output')
    args = parser.parse_args()
    if args.mode == 'packet':
        result = packet(args.video, args.temporal, args.boundary, args.evidence,
                        args.audit, args.output, args.regions)
    elif args.mode == 'template':
        result = template(args.packet, args.output)
    else:
        result = annotate(args.packet, args.annotations, args.output)
    print(json.dumps(result.get('counts', {'annotations': len(result.get('annotations', []))})))


if __name__ == '__main__':
    main()
