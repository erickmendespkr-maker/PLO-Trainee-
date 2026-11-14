"""Audit annotation intervals against sampled frames; samples never prove a hand."""
import json
import math
from pathlib import Path
try:
    from .offline_hand_annotation import validate_annotations
except ImportError:
    from offline_hand_annotation import validate_annotations

def audit_annotation_evidence(bundle, annotations, *, require_samples=True):
    validated = validate_annotations(bundle, annotations)
    timeline = bundle.get('timeline')
    if not isinstance(timeline, dict) or timeline.get('status') != 'UNREVIEWED_TIMELINE':
        raise ValueError('missing unreviewed timeline')
    for flag in ('absolute_source_pts_verified', 'hand_boundaries_verified', 'ocr_verified', 'equity_ev_verified'):
        if timeline.get(flag) is not False:
            raise ValueError('unsupported verification')
    events = timeline.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('missing events')
    indexed, identities = {}, set()
    for event in events:
        if not isinstance(event, dict) or event.get('review_status') != 'UNREVIEWED':
            raise ValueError('invalid event')
        tid, idx, pts, digest = (event.get(k) for k in ('table_id', 'frame_index', 'crop_pts_seconds', 'rgb_sha256'))
        if type(tid) is not int or tid not in range(1, 5) or type(idx) is not int or idx < 0:
            raise ValueError('invalid table/frame')
        if type(pts) not in (int, float) or not math.isfinite(pts) or pts < 0:
            raise ValueError('invalid timestamp')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid hash')
        if (tid, idx) in identities:
            raise ValueError('duplicate evidence')
        identities.add((tid, idx))
        nominal = event.get('nominal_source_seconds')
        if nominal is not None:
            if type(nominal) not in (int, float) or not math.isfinite(nominal) or nominal < pts:
                raise ValueError('invalid nominal source timestamp')
            if event.get('nominal_source_seconds_verified') is not False:
                raise ValueError('nominal source time cannot be verified')
        elif 'nominal_source_seconds_verified' in event:
            raise ValueError('nominal verification flag without timestamp')
        indexed.setdefault(tid, []).append((pts, idx, digest, nominal))
    for samples in indexed.values():
        samples.sort()
        if any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
            raise ValueError('nonmonotonic PTS')
    results = []
    for hand in validated['hands']:
        table = hand['table_id']
        if not table.isascii() or not table.isdecimal() or str(int(table)) != table:
            raise ValueError('noncanonical table ID')
        tid = int(table)
        if tid not in indexed:
            raise ValueError('absent table')
        start, end = hand['start_seconds'], hand['end_seconds']
        # Annotation intervals are nominal source seconds when a crop offset exists.\n        # Never compare them to crop-relative PTS in that case.\n        modes = {sample[3] is not None for sample in indexed[tid]}\n        if len(modes) != 1:\n            raise ValueError('mixed timestamp coordinate systems')\n        samples = [s for s in indexed[tid] if start <= (s[3] if True in modes else s[0]) <= end]
        if require_samples and not samples:
            raise ValueError('interval without sampled frames')
        results.append({'table_id': tid, 'hand_id': hand['hand_id'],
                        'sample_count': len(samples), 'sample_frame_indices': [s[1] for s in samples],
                        'sample_rgb_sha256': [s[2] for s in samples],
                        'interval_seconds': [start, end],
                        'temporal_sample_coverage_only': bool(samples),
                        'hand_identity_verified': False, 'cards_visually_verified': False,
                        'action_visually_verified': False, 'equity_ev_verified': False})
    return {'status': 'ANNOTATION_TEMPORAL_EVIDENCE_AUDIT_ONLY',
            'evidence_json_sha256': validated['evidence_json_sha256'],
            'hands': results, 'source_absolute_pts_verified': False,
            'hands_verified': False, 'equity_ev_verified': False}

def write_audit(bundle_path, annotations_path, output_path, *, require_samples=True):
    src, ann, dst = map(Path, (bundle_path, annotations_path, output_path))
    if any(p.is_symlink() for p in (src, ann, dst)) or len({p.resolve() for p in (src, ann, dst)}) != 3:
        raise ValueError('unsafe paths')
    result = audit_annotation_evidence(json.loads(src.read_text(encoding='utf-8')),
                                       json.loads(ann.read_text(encoding='utf-8')),
                                       require_samples=require_samples)
    with dst.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result
