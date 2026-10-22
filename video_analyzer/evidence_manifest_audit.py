"""Validate provenance and nominal time grid of offline frame evidence.

This is a consistency audit, not a frame recognizer or exact source-PTS check.
It never promotes sampled images or OCR to confirmed events.
"""
import json
import math
from pathlib import Path, PurePosixPath


def _positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be finite and positive')
    return float(value)


def audit_manifest(manifest, *, image_root=None):
    """Return issues without interpreting visual content.

    Rejects malformed manifests; reports grid drift, missing images and duplicate
    samples as issues. Image paths must be relative and cannot use symlinks.
    """
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ValueError('Expected evidence manifest schema version 1')
    if (manifest.get('analysis_status') != 'unverified_visual_evidence_only'
            or manifest.get('requires_manual_review') is not True
            or manifest.get('timestamp_semantics') != 'nominal_sampling_grid_not_exact_source_pts'):
        raise ValueError('Only unverified nominal-timestamp evidence is accepted')
    interval = _positive(manifest.get('interval_seconds'), 'interval_seconds')
    recording = manifest.get('recording')
    if not isinstance(recording, dict):
        raise ValueError('Missing recording metadata')
    duration = _positive(recording.get('duration_seconds'), 'recording duration')
    regions = manifest.get('regions')
    if not isinstance(regions, list) or not 1 <= len(regions) <= 4:
        raise ValueError('Expected one to four regions')
    table_ids = [r.get('table_id') for r in regions if isinstance(r, dict)]
    if (len(table_ids) != len(regions) or any(isinstance(t, bool) or not isinstance(t, int)
            or not 1 <= t <= 4 for t in table_ids) or len(set(table_ids)) != len(table_ids)):
        raise ValueError('Invalid or duplicate table IDs')
    frames = manifest.get('frames')
    if not isinstance(frames, list) or not 1 <= len(frames) <= 40000:
        raise ValueError('Expected 1..40000 frames')
    issues, paths, counts, last_times = [], set(), {t: 0 for t in table_ids}, {}
    root = Path(image_root).resolve(strict=True) if image_root is not None else None
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f'Invalid frame {index}')
        table = frame.get('table_id')
        if isinstance(table, bool) or table not in counts:
            raise ValueError(f'Unknown table ID in frame {index}')
        stamp = frame.get('nominal_timestamp_seconds')
        if (isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp) or stamp < 0):
            raise ValueError(f'Invalid frame timestamp {index}')
        if frame.get('status') != 'unverified_visual_evidence':
            raise ValueError(f'Frame {index} must remain unverified')
        name = frame.get('image')
        if not isinstance(name, str) or '\\' in name or not name:
            raise ValueError(f'Invalid image path {index}')
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or len(path.parts) != 2
                or path.parts[0] != f'table_{table:02d}'
                or not path.parts[1].startswith('frame_') or path.suffix.lower() != '.png'):
            raise ValueError(f'Unsafe or mismatched image path {index}')
        if name in paths:
            issues.append({'index': index, 'reason': 'duplicate_image_path'})
        paths.add(name)
        if stamp + 1e-8 < last_times.get(table, -1.):
            issues.append({'index': index, 'reason': 'out_of_order_timestamp'})
        last_times[table] = stamp
        expected = counts[table] * interval
        if not math.isclose(stamp, expected, abs_tol=1e-6, rel_tol=1e-8):
            issues.append({'index': index, 'reason': 'nominal_grid_mismatch', 'expected_seconds': expected})
        if stamp > duration + interval / 2 + 1e-6:
            issues.append({'index': index, 'reason': 'timestamp_beyond_recording'})
        counts[table] += 1
        if root is not None:
            file = root.joinpath(*path.parts)
            if file.is_symlink() or file.parent.is_symlink() or not file.is_file():
                issues.append({'index': index, 'reason': 'missing_or_unsafe_image'})
    return {'schema_version': 1, 'analysis_status': 'unverified_evidence_audit',
            'frame_count': len(frames), 'table_count': len(table_ids),
            'frames_per_table': {str(k): v for k, v in sorted(counts.items())},
            'nominal_timestamps_only': True, 'source_pts_verified': False,
            'requires_manual_review': True, 'issues': issues,
            'consistent': not issues}


def audit_manifest_file(manifest_path, output_path, *, check_images=True):
    source = Path(manifest_path)
    payload = json.loads(source.read_text(encoding='utf-8'))
    report = audit_manifest(payload, image_root=source.parent if check_images else None)
    destination = Path(output_path)
    if destination.resolve() == source.resolve():
        raise ValueError('Audit must not overwrite evidence manifest')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('output')
    args = parser.parse_args()
    result = audit_manifest_file(args.manifest, args.output)
    print(json.dumps({'consistent': result['consistent'], 'issues': len(result['issues'])}))
    raise SystemExit(0 if result['consistent'] else 1)
