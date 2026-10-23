"""Pure, bounded indexing of activity-selected frames (no poker inference).

The caller MUST separately audit PNG bytes against their SHA-256 manifest.
Grouping repeated seeks is not evidence of actions or authenticated capture time.
"""
from fractions import Fraction
import math
import re

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_IMAGE = re.compile(r'table_(0[1-4])/frame_\d{5}\.png\Z')


def index_activity_frames(manifest):
    """Return distinct table-frame anchors, preserving all requested seeks.

    Reject inconsistent PTS, reused images with different anchors, and repeated
    seek requests. This function does NOT read or authenticate PNG files.
    """
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
            or manifest.get('analysis_status') != 'unverified_activity_pts_evidence_only'
            or manifest.get('timestamp_semantics') != 'decoded_filtergraph_pts_not_capture_time'
            or manifest.get('requires_manual_review') is not True):
        raise ValueError('Unsupported activity evidence manifest')
    try:
        base = Fraction(manifest['source_time_base'])
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError('Invalid PTS timebase') from exc
    if base <= 0:
        raise ValueError('Invalid PTS timebase')
    frames = manifest.get('frames')
    missing = manifest.get('unresolved')
    if (not isinstance(frames, list) or not isinstance(missing, list)
            or len(frames) + len(missing) > 600
            or type(manifest.get('requested_count')) is not int
            or manifest['requested_count'] != len(frames) + len(missing)):
        raise ValueError('Invalid activity evidence counts')
    by_image, seen_seeks = {}, set()
    for row in frames:
        if not isinstance(row, dict) or row.get('status') != 'unverified_visual_evidence':
            raise ValueError('Invalid frame')
        table, name = row.get('table_id'), row.get('image')
        if (type(table) is not int or table not in (1, 2, 3, 4)
                or not isinstance(name, str) or not _IMAGE.fullmatch(name)
                or int(name[6:8]) != table):
            raise ValueError('Invalid table image path')
        sha, ticks = row.get('sha256'), row.get('source_pts_ticks')
        t, seek = row.get('timestamp_seconds'), row.get('requested_seek_seconds')
        if (not isinstance(sha, str) or not _SHA.fullmatch(sha)
                or type(ticks) is not int or ticks < 0
                or type(t) not in (int, float) or not math.isfinite(t) or t < 0
                or type(seek) not in (int, float) or not math.isfinite(seek) or seek < 0
                or not math.isclose(t, float(ticks * base), abs_tol=1e-6, rel_tol=1e-10)
                or t + 1e-6 < seek):
            raise ValueError('Invalid PTS, seek or digest')
        if row.get('seek_reason') not in ('baseline_grid', 'unverified_activity_neighborhood'):
            raise ValueError('Invalid unverified seek reason')
        seek_key = (table, seek)
        if seek_key in seen_seeks:
            raise ValueError('Duplicate table seek')
        seen_seeks.add(seek_key)
        key = (table, name)
        anchor = (ticks, t, sha)
        if key in by_image:
            if by_image[key]['_anchor'] != anchor:
                raise ValueError('Conflicting PTS/hash for shared decoded frame')
            by_image[key]['requested_seeks'].append(seek)
            by_image[key]['seek_reasons'].append(row['seek_reason'])
        else:
            by_image[key] = {'table_id': table, 'source_image': name,
                             'source_sha256': sha, 'source_pts_ticks': ticks,
                             'timestamp': t, '_anchor': anchor,
                             'requested_seeks': [seek],
                             'seek_reasons': [row['seek_reason']]}
    for row in missing:
        if (not isinstance(row, dict) or row.get('reason') != 'no_decoded_frame_within_seek_drift'
                or type(row.get('table_id')) is not int
                or row['table_id'] not in (1, 2, 3, 4)
                or type(row.get('requested_seek_seconds')) not in (int, float)
                or not math.isfinite(row['requested_seek_seconds'])
                or row['requested_seek_seconds'] < 0):
            raise ValueError('Invalid unresolved seek')
        key = (row['table_id'], row['requested_seek_seconds'])
        if key in seen_seeks:
            raise ValueError('Duplicate resolved/unresolved seek')
        seen_seeks.add(key)
    return [{k: v for k, v in item.items() if k != '_anchor'}
            for item in sorted(by_image.values(),
                               key=lambda r: (r['timestamp'], r['table_id'], r['source_image']))]
