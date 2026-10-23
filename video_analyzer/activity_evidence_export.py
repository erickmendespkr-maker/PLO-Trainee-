"""Offline, review-only FFmpeg extraction of activity-planned table evidence.

Consumes requested times from an unverified activity plan, decodes original
presentation timestamps (PTS) with showinfo, and hashes PNG table crops.
A requested seek is *not* a source PTS, a poker action, or proof of OCR.
This module does not contact networks or interact with live poker software.
"""
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from table_regions import Region, grid_regions, validate_regions
from video_validator import validate_recording
from activity_pts_mapping import resolve_requested_pts

_HEX = re.compile(r'^[0-9a-f]{64}$')
_BASE = re.compile(r'\bconfig in time_base:\s*(\d+/\d+)')
_PTS = re.compile(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:')


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _real(value, label, low=0., *, strict=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= low if strict else value < low)):
        raise ValueError(f'Invalid {label}')
    return float(value)


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {label}')
    return value


def _validate_plan(plan, duration, sha, max_requests):
    if (not isinstance(plan, dict) or plan.get('schema_version') != 1
            or plan.get('analysis_status') != 'requested_offline_seek_plan_only'
            or plan.get('timestamp_semantics') != 'requested_seek_seconds_not_decoded_source_pts'
            or plan.get('requires_manual_review') is not True
            or plan.get('recording_sha256') != sha):
        raise ValueError('Untrusted or incompatible activity plan/recording')
    if not math.isclose(_real(plan.get('duration_seconds'), 'plan duration', strict=True),
                        duration, abs_tol=.15, rel_tol=0):
        raise ValueError('Plan duration does not match source recording')
    tables = plan.get('tables')
    if not isinstance(tables, list) or not 1 <= len(tables) <= 4:
        raise ValueError('Expected 1..4 planned tables')
    requests, table_ids = {}, []
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError('Invalid table')
        table_id = _integer(table.get('table_id'), 'table ID', 1, 4)
        if table_id in table_ids:
            raise ValueError('Repeated table ID')
        table_ids.append(table_id)
        frames = table.get('requested_frames')
        if not isinstance(frames, list) or not frames:
            raise ValueError('Each table needs at least one requested frame')
        if table.get('planned_count') != len(frames):
            raise ValueError('Plan count mismatch')
        previous = -1.
        for row in frames:
            if not isinstance(row, dict) or row.get('reason') not in (
                    'baseline_grid', 'unverified_activity_neighborhood'):
                raise ValueError('Invalid seek reason')
            t = _real(row.get('requested_seek_seconds'), 'requested seek')
            if t >= duration or t <= previous:
                raise ValueError('Seek times must be ordered, unique and within duration')
            previous = t
            requests.setdefault(table_id, []).append((t, row['reason']))
    if (plan.get('planned_total_frames') != sum(map(len, requests.values()))
            or sum(map(len, requests.values())) > max_requests):
        raise ValueError('Plan exceeds extraction budget or has inconsistent counts')
    return requests


def _showinfo(stderr):
    bases = _BASE.findall(stderr)
    if len(bases) != 1:
        raise RuntimeError('Expected exactly one FFmpeg showinfo time base')
    base = Fraction(bases[0])
    if base <= 0:
        raise RuntimeError('Invalid FFmpeg time base')
    matches = _PTS.findall(stderr)
    if not matches:
        raise RuntimeError('FFmpeg returned no decoded frames')
    rows = []
    for i, (n, ticks) in enumerate(matches):
        if int(n) != i:
            raise RuntimeError('FFmpeg frame numbering inconsistent')
        pts = int(ticks)
        t = float(pts * base)
        if pts < 0 or not math.isfinite(t) or (rows and t <= rows[-1][1]):
            raise RuntimeError('Invalid or non-monotonic source PTS')
        rows.append((pts, t))
    return str(base), rows


def export_activity_evidence(recording, plan, output_dir, *, regions=None,
                             max_requests=600, max_unique_times=600,
                             max_seek_drift_seconds=2., ffmpeg_timeout_seconds=600):
    """Export PNG crops for planned seeks and an auditable PTS manifest.

    Decodes once using a bounded FFmpeg select filter. Multiple requested
    times may resolve to the same source frame; unmatched times are reported.
    Output directory must not exist. No guessed PTS or confirmed poker events.
    """
    max_requests = _integer(max_requests, 'max requests', 1, 600)
    max_unique_times = _integer(max_unique_times, 'max unique times', 1, 600)
    timeout = _integer(ffmpeg_timeout_seconds, 'FFmpeg timeout', 1, 3600)
    drift = _real(max_seek_drift_seconds, 'maximum seek drift', strict=True)
    if drift > 30:
        raise ValueError('Seek drift above 30 seconds is not supported')
    source = Path(recording)
    info = validate_recording(source)
    before = _digest(source)
    if isinstance(plan, (str, Path)):
        plan = json.loads(Path(plan).read_text(encoding='utf-8'))
    requests = _validate_plan(plan, info['duration_seconds'], before, max_requests)
    if regions is None:
        regions = grid_regions(info['width'], info['height'])
        regions = [r for r in regions if r.table_id in requests]
    if (not isinstance(regions, (tuple, list)) or len(regions) != len(requests)
            or any(not isinstance(r, Region) for r in regions)
            or {r.table_id for r in regions} != set(requests)):
        raise ValueError('Plan and region table IDs must match')
    validate_regions(regions, info['width'], info['height'])
    unique = sorted({t for rows in requests.values() for t, _ in rows})
    if len(unique) > max_unique_times:
        raise ValueError('Unique seek count exceeds decode budget')
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError('Evidence output already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # prev_selected_t is from the source select filter. For each target,
    # emit only the first decoded frame at/after it. This does not use FPS
    # resampling, so showinfo reports the decoded filtergraph source PTS.
    expr = '+'.join(
        f'gte(t,{t:.9f})*(isnan(prev_selected_t)+lt(prev_selected_t,{t:.9f}))'
        for t in unique)
    names = ''.join(f'[t{i}]' for i in range(len(regions)))
    graph = [f'[0:v:0]select={expr!r},showinfo,split={len(regions)}{names}']
    for i, r in enumerate(regions):
        graph.append(f'[t{i}]crop={r.width}:{r.height}:{r.x}:{r.y}[o{i}]')
    with tempfile.TemporaryDirectory(prefix='plo_activity_pts_', dir=destination.parent) as tempdir:
        scratch = Path(tempdir)
        cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-loglevel', 'info',
               '-i', str(source), '-filter_complex', ';'.join(graph)]
        for i, r in enumerate(regions):
            folder = scratch / f'table_{r.table_id:02d}'
            folder.mkdir()
            cmd.extend(['-map', f'[o{i}]', '-frames:v', str(len(unique)),
                        '-fps_mode', 'passthrough', '-threads:v', '1',
                        '-start_number', '0', str(folder / 'frame_%05d.png')])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=True)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('FFmpeg offline activity extraction timed out') from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError('FFmpeg offline activity extraction failed') from exc
        timebase, decoded = _showinfo(proc.stderr)
        if len(decoded) > len(unique):
            raise RuntimeError('FFmpeg emitted more frames than requested seeks')
        if _digest(source) != before:
            raise RuntimeError('Source recording changed during extraction')
        frames, unresolved = [], []
        for r in regions:
            folder = scratch / f'table_{r.table_id:02d}'
            pngs = sorted(folder.glob('frame_*.png'))
            if len(pngs) != len(decoded):
                raise RuntimeError('FFmpeg output count and PTS count disagree')
            requested = requests[r.table_id]
            mapped, missing = resolve_requested_pts(
                [t for t, _ in requested], decoded, max_drift_seconds=drift)
            unresolved.extend({'table_id': r.table_id, **item} for item in missing)
            selected = set()
            reasons = {t: reason for t, reason in requested}
            for match in mapped:
                ix = match['frame_index']
                selected.add(ix)
                frames.append({'table_id': r.table_id,
                               'requested_seek_seconds': match['requested_seek_seconds'],
                               'seek_reason': reasons[match['requested_seek_seconds']],
                               'image': f'table_{r.table_id:02d}/frame_{ix:05d}.png',
                               'source_pts_ticks': match['source_pts_ticks'],
                               'timestamp_seconds': match['timestamp_seconds'],
                               'seek_drift_seconds': match['seek_drift_seconds'],
                               'status': 'unverified_visual_evidence',
                               'sha256': _digest(pngs[ix])})
            for ix, image in enumerate(pngs):
                if ix not in selected:
                    image.unlink()
        manifest = {
            'schema_version': 1,
            'analysis_status': 'unverified_activity_pts_evidence_only',
            'timestamp_semantics': 'decoded_filtergraph_pts_not_capture_time',
            'selection_policy': 'first_decoded_frame_at_or_after_requested_seek',
            'requires_manual_review': True,
            'recording_sha256': before, 'recording_duration_seconds': info['duration_seconds'],
            'source_time_base': timebase, 'max_seek_drift_seconds': drift,
            'requested_count': sum(map(len, requests.values())),
            'resolved_count': len(frames), 'unresolved_count': len(unresolved),
            'unique_decoded_frames': len(decoded),
            'regions': [asdict(r) for r in regions],
            'frames': frames, 'unresolved': unresolved,
            'warning': ('Decoded PTS are not authenticated capture times. Pixel activity '
                        'does not prove poker actions. OCR, hands, equity and EV require '
                        'independent review and stated assumptions.'),
        }
        (scratch / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        scratch.rename(destination)
    return manifest


def audit_activity_evidence(manifest, root):
    """Verify hashes, paths, PTS arithmetic and counts; never certify poker actions."""
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
            or manifest.get('analysis_status') != 'unverified_activity_pts_evidence_only'
            or manifest.get('requires_manual_review') is not True
            or manifest.get('timestamp_semantics') != 'decoded_filtergraph_pts_not_capture_time'):
        raise ValueError('Unsupported activity evidence manifest')
    try:
        base = Fraction(manifest['source_time_base'])
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        raise ValueError('Invalid PTS time base') from exc
    if base <= 0:
        raise ValueError('Invalid PTS time base')
    source_sha = manifest.get('recording_sha256')
    if not isinstance(source_sha, str) or not _HEX.fullmatch(source_sha):
        raise ValueError('Invalid source hash')
    duration = _real(manifest.get('recording_duration_seconds'),
                     'recording duration', strict=True)
    max_drift = _real(manifest.get('max_seek_drift_seconds'),
                      'maximum seek drift', strict=True)
    if max_drift > 30:
        raise ValueError('Invalid maximum seek drift')
    frames, unresolved = manifest.get('frames'), manifest.get('unresolved')
    if (not isinstance(frames, list) or not isinstance(unresolved, list)
            or len(frames) > 600 or len(unresolved) > 600
            or manifest.get('resolved_count') != len(frames)
            or manifest.get('unresolved_count') != len(unresolved)
            or manifest.get('requested_count') != len(frames) + len(unresolved)):
        raise ValueError('Inconsistent evidence counts')
    root = Path(root).resolve(strict=True)
    issues, verified = [], set()
    for idx, row in enumerate(frames):
        if not isinstance(row, dict) or row.get('status') != 'unverified_visual_evidence':
            raise ValueError('Invalid evidence row')
        table = _integer(row.get('table_id'), 'table ID', 1, 4)
        name = row.get('image')
        if (not isinstance(name, str) or not re.fullmatch(
                rf'table_{table:02d}/frame_\d{{5}}\.png', name)):
            raise ValueError('Unsafe evidence image path')
        image = root / name
        if not image.resolve().is_relative_to(root) or not image.is_file():
            issues.append({'index': idx, 'reason': 'missing_or_external_image'})
            continue
        sha = row.get('sha256')
        if not isinstance(sha, str) or not _HEX.fullmatch(sha):
            raise ValueError('Invalid image SHA-256')
        if _digest(image) != sha:
            issues.append({'index': idx, 'reason': 'image_hash_mismatch'})
        ticks = _integer(row.get('source_pts_ticks'), 'source PTS', 0, 2**63-1)
        t = _real(row.get('timestamp_seconds'), 'decoded timestamp')
        requested = _real(row.get('requested_seek_seconds'), 'requested seek')
        if requested >= duration:
            raise ValueError('Seek beyond recording duration')
        drift = _real(row.get('seek_drift_seconds'), 'seek drift', low=-1e-5)
        if (not math.isclose(t, float(ticks * base), abs_tol=1e-6, rel_tol=1e-10)
                or not math.isclose(t - requested, drift, abs_tol=1e-6)
                or drift > max_drift + 1e-6):
            issues.append({'index': idx, 'reason': 'pts_or_seek_mismatch'})
        key = (table, requested)
        if key in verified:
            issues.append({'index': idx, 'reason': 'duplicate_seek'})
        verified.add(key)
    for idx, row in enumerate(unresolved):
        if not isinstance(row, dict) or row.get('reason') != 'no_decoded_frame_within_seek_drift':
            raise ValueError('Invalid unresolved seek')
        table = _integer(row.get('table_id'), 'unresolved table ID', 1, 4)
        requested = _real(row.get('requested_seek_seconds'), 'unresolved seek')
        if requested >= duration:
            raise ValueError('Unresolved seek beyond duration')
        key = (table, requested)
        if key in verified:
            issues.append({'index': idx, 'reason': 'duplicate_resolved_or_unresolved_seek'})
        verified.add(key)
    return {'ok': not issues, 'issues': issues, 'verified_rows': len(frames),
            'requires_manual_review': True}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('activity_plan_json')
    parser.add_argument('output_directory')
    parser.add_argument('--regions-json')
    args = parser.parse_args()
    rois = None
    if args.regions_json:
        rois = [Region(**row) for row in json.loads(
            Path(args.regions_json).read_text(encoding='utf-8'))]
    report = export_activity_evidence(args.recording, args.activity_plan_json,
                                      args.output_directory, regions=rois)
    print(json.dumps({'requested': report['requested_count'],
                      'resolved': report['resolved_count'],
                      'unresolved': report['unresolved_count']}))
