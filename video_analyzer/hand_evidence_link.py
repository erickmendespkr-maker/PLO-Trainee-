"""Offline, fail-closed navigation from human hand annotations to audited PNGs.

This is an evidence *lookup*, NOT independent validation of cards, hands,
OCR, timestamps, equity, EV, or strategy. Only existing PTS-byte-matched
frames in the boundary review packet are eligible as nearby references.
The original packet, navigation and manual-review report must all be supplied.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from boundary_hand_draft import _read, _write, build_template, validate_review
from boundary_history_bridge import FALSE

MAX_TASKS = 2048
MAX_FRAMES = 120
MAX_SECONDS = 7200
TOLERANCE_SECONDS = 0.25
PNG_NAME = re.compile(r'table_(0[1-4])_seek_([0-9]{4})\.png\Z')


def _hex64(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def _second(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= MAX_SECONDS


def _frames(packet, evidence_dir):
    """Validate candidate frames against local bytes; no re-decode claim."""
    if (not isinstance(packet, dict) or packet.get('schema_version') != 1
            or packet.get('analysis_status') != 'candidate_boundary_review_only'
            or packet.get('requires_manual_review') is not True
            or any(packet.get(key) is not False for key in FALSE)):
        raise ValueError('Invalid boundary packet or authority flags')
    tasks = packet.get('tasks')
    if not isinstance(tasks, list) or len(tasks) > MAX_TASKS:
        raise ValueError('Invalid task budget')
    root = Path(evidence_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Evidence directory must be a real directory')
    by_task, file_digests = {}, {}
    total_frames = 0
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('Invalid task')
        tid, table, frames = task.get('task_id'), task.get('table_id'), task.get('frames')
        if (not isinstance(tid, str) or not tid or len(tid) > 200 or tid in by_task
                or type(table) is not int or not 1 <= table <= 4
                or not isinstance(frames, list)):
            raise ValueError('Invalid/duplicate task')
        total_frames += len(frames)
        if total_frames > MAX_FRAMES * MAX_TASKS:
            raise ValueError('Too many frame references')
        refs, seen = [], set()
        for frame in frames:
            if not isinstance(frame, dict):
                raise ValueError('Invalid frame')
            fid, filename = frame.get('frame_id'), frame.get('filename')
            name_match = PNG_NAME.fullmatch(filename) if isinstance(filename, str) else None
            sha, pts = frame.get('png_sha256'), frame.get('decoded_pts_seconds')
            if (type(fid) is not int or fid < 0 or fid in seen
                    or name_match is None or int(name_match.group(1)) != table
                    or int(name_match.group(2)) != fid
                    or not _hex64(sha) or type(frame.get('pts_byte_matched')) is not bool
                    or (pts is not None and not _second(pts))):
                raise ValueError('Invalid frame metadata')
            seen.add(fid)
            # Check even unmatched frames so forged/broken provenance is visible.
            image = root / filename
            if image.is_symlink() or not image.is_file() or image.stat().st_size > 20_000_000:
                raise ValueError('Missing, symlinked or oversized PNG evidence')
            if filename not in file_digests:
                data = image.read_bytes()
                if not data.startswith(bytes.fromhex('89504e470d0a1a0a')):
                    raise ValueError('Evidence is not a PNG')
                file_digests[filename] = hashlib.sha256(data).hexdigest()
                if len(file_digests) > MAX_FRAMES:
                    raise ValueError('Too many distinct evidence frames')
            if file_digests[filename] != sha:
                raise ValueError('PNG evidence SHA-256 mismatch')
            if frame['pts_byte_matched'] and pts is None:
                raise ValueError('Matched frame lacks decoded PTS')
            if frame['pts_byte_matched']:
                refs.append({'task_id': tid, 'frame_id': fid, 'filename': filename,
                             'png_sha256': sha, 'decoded_pts_seconds': pts})
        by_task[tid] = (table, refs)
    return by_task


def _lookup(kind, confirmed, pts, refs):
    if kind == 'hypothesis':
        return {'status': 'hypothesis_not_evidence', 'candidate_frames': []}
    if kind == 'unknown':
        return {'status': 'unknown', 'candidate_frames': []}
    if pts is None:
        return {'status': 'no_source_timestamp', 'candidate_frames': []}
    candidates = []
    for frame in refs:
        delta = abs(frame['decoded_pts_seconds'] - pts)
        if delta <= TOLERANCE_SECONDS:
            candidates.append({**frame, 'absolute_delta_seconds': round(delta, 6)})
    candidates.sort(key=lambda f: (f['absolute_delta_seconds'], f['task_id'], f['frame_id']))
    if not candidates:
        status = 'no_nearby_byte_matched_frame'
    elif confirmed:
        status = 'nearby_frame_for_human_claim_not_content_verified'
    else:
        status = 'nearby_frame_for_unconfirmed_entry'
    return {'status': status, 'candidate_frames': candidates[:8]}


def build(navigation, navigation_sha, packet, packet_sha, review, evidence_dir):
    """Cross-check the three linked reports and emit conservative references."""
    template = build_template(navigation, navigation_sha)
    if (navigation.get('source_packet_sha256') != packet_sha
            or packet.get('recording_sha256') != navigation.get('recording_sha256')):
        raise ValueError('Packet digest or recording does not match navigation')
    if (not isinstance(review, dict) or not isinstance(review.get('entries'), list)
            or review.get('analysis_status') != 'manual_hand_history_review_unverified_no_math'):
        raise ValueError('Invalid reviewed report')
    # The original validator protects metadata, field semantics and action order.
    editable = {**template, 'entries': review['entries']}
    if validate_review(navigation, navigation_sha, editable) != review:
        raise ValueError('Review report does not match revalidated original')
    by_task = _frames(packet, evidence_dir)
    result_entries = []
    for entry in review['entries']:
        ids = entry['source_task_ids'] + entry['interior_candidate_ids']
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate source task reference')
        refs = []
        for tid in ids:
            if tid not in by_task or by_task[tid][0] != entry['table_id']:
                raise ValueError('Missing or cross-table task reference')
            refs.extend(by_task[tid][1])
        refs = [f for f in refs if entry['start_human_seconds'] <= f['decoded_pts_seconds'] <= entry['end_human_seconds']]
        fields = {}
        for name, value in entry['fields'].items():
            fields[name] = _lookup(value['source_kind'], value['human_confirmed'],
                                   value['source_pts_seconds'], refs)
        actions = []
        for i, action in enumerate(entry['actions']):
            actions.append({'action_index': i, **_lookup(action['source_kind'],
                            action['human_confirmed'], action['timestamp_seconds'], refs)})
        result_entries.append({'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
                               'field_links': fields, 'action_links': actions,
                               'frame_references_in_span': len(refs)})
    return {'schema_version': 1,
            'analysis_status': 'manual_hand_evidence_lookup_only_no_math',
            'recording_sha256': navigation['recording_sha256'],
            'source_navigation_sha256': navigation_sha,
            'source_boundary_packet_sha256': packet_sha,
            'entries': result_entries, 'tolerance_seconds': TOLERANCE_SECONDS,
            'timestamp_semantics': 'ffmpeg_filtergraph_pts_not_wall_clock',
            'evidence_limitation': ('PNG bytes are rehashed locally; this lookup does not '
                                    're-decode video or establish cards/actions/hand boundaries.'),
            'requires_manual_review': True, **{k: False for k in FALSE}}


def export(navigation_path, packet_path, review_path, evidence_dir, output_path):
    navigation, navigation_sha = _read(navigation_path)
    packet, packet_sha = _read(packet_path)
    review, _ = _read(review_path)
    destination = Path(output_path)
    inputs = [Path(navigation_path), Path(packet_path), Path(review_path)]
    root = Path(evidence_dir)
    if (destination.resolve() in {p.resolve() for p in inputs}
            or destination.resolve().is_relative_to(root.resolve())):
        raise ValueError('Unsafe output path')
    result = build(navigation, navigation_sha, packet, packet_sha, review, root)
    _write(destination, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('navigation')
    parser.add_argument('packet')
    parser.add_argument('review')
    parser.add_argument('evidence_dir')
    parser.add_argument('output')
    args = parser.parse_args(argv)
    result = export(args.navigation, args.packet, args.review, args.evidence_dir, args.output)
    print(json.dumps({'status': result['analysis_status'], 'entries': len(result['entries'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
