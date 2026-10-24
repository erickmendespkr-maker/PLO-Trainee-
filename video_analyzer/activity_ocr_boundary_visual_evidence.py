"""Offline FFmpeg navigation evidence for *unverified* OCR hand-transition windows.

Recomputes the boundary triage from its temporal OCR source, validates the
recording hash and optionally crops manually specified table rectangles.
Requested seek times are NEVER represented as verified decoded timestamps.
No hand, action, equity, EV or automatic clip is authorized by this module.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from activity_ocr_boundary_triage import build_ocr_boundary_triage
from video_validator import validate_recording

STATUS = 'unverified_ocr_boundary_navigation_images_only'


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected regular non-symlink input')
    return path


def _regions(regions, width, height):
    if regions is None:
        return {}
    if not isinstance(regions, dict) or len(regions) > 4:
        raise ValueError('Expected at most four manually defined table regions')
    out = {}
    for key, rect in regions.items():
        if key not in ('1', '2', '3', '4') or not isinstance(rect, dict) or set(rect) != {'x', 'y', 'width', 'height'}:
            raise ValueError('Invalid table region')
        if any(type(rect[k]) is not int for k in rect):
            raise ValueError('Table coordinates must be integers')
        x, y, w, h = (rect[k] for k in ('x', 'y', 'width', 'height'))
        if x < 0 or y < 0 or w < 2 or h < 2 or x + w > width or y + h > height:
            raise ValueError('Table region exceeds video dimensions')
        out[int(key)] = dict(rect)
    return out


def build_boundary_visual_plan(video_path, temporal_report, boundary_report, *,
                               temporal_sha256, max_frames=60, samples_per_window=3,
                               table_regions=None):
    """Prepare bounded seek requests with no claim about actual decoded PTS."""
    if type(max_frames) is not int or not 1 <= max_frames <= 120:
        raise ValueError('Invalid frame budget')
    if type(samples_per_window) is not int or not 1 <= samples_per_window <= 3:
        raise ValueError('Invalid samples per window')
    if not isinstance(temporal_sha256, str) or len(temporal_sha256) != 64 or any(c not in '0123456789abcdef' for c in temporal_sha256):
        raise ValueError('Invalid temporal report hash')
    expected = build_ocr_boundary_triage(temporal_report, source_sha256=temporal_sha256)
    if boundary_report != expected:
        raise ValueError('Boundary report differs from recomputed OCR evidence')
    video = _regular(video_path)
    info = validate_recording(video)
    recording_sha = _sha(video)
    if recording_sha != expected['recording_sha256']:
        raise ValueError('Recording hash mismatch')
    duration = info['duration_seconds']
    rects = _regions(table_regions, info['width'], info['height'])
    windows = sorted(enumerate(expected['review_windows']),
                     key=lambda x: (x[1]['priority'] != 'review_first', x[1]['table_id'],
                                    x[1]['review_window_start_seconds'], x[0]))
    frames, associations, skipped = [], [], []
    by_key = {}
    for index, window in windows:
        start, end = window['review_window_start_seconds'], window['review_window_end_seconds']
        table = window['table_id']
        if not (0 <= start < end < duration):
            skipped.append({'window_index': index, 'reason': 'window_outside_recording_duration'})
            continue
        points = ([start] if samples_per_window == 1 else
                  [start, end] if samples_per_window == 2 else [start, (start + end) / 2, end])
        ids = []
        for seek in points:
            seek = round(seek, 6)
            key = (table, seek)
            if key not in by_key:
                if len(frames) >= max_frames:
                    continue
                frame_id = len(frames)
                by_key[key] = frame_id
                frames.append({'frame_id': frame_id, 'table_id': table,
                               'requested_seek_seconds': seek,
                               'decoded_pts_seconds': None, 'decoded_pts_verified': False,
                               'region': rects.get(table), 'sha256': None,
                               'filename': f'table_{table:02d}_seek_{frame_id:04d}.png',
                               'status': 'planned_not_decoded'})
            ids.append(by_key[key]) if key in by_key else None
        if ids:
            associations.append({'window_index': index, 'table_id': table,
                                 'priority': window['priority'], 'frame_ids': ids,
                                 'requires_manual_review': True})
        if len(ids) < len(points):
            skipped.append({'window_index': index, 'reason': 'frame_budget_exceeded',
                            'planned': len(ids), 'requested': len(points)})
    return {'schema_version': 1, 'analysis_status': STATUS,
            'recording_sha256': recording_sha,
            'source_temporal_report_sha256': temporal_sha256,
            'source_boundary_report_sha256': None,  # set by file-based exporter
            'roi_profile_sha256': expected['roi_profile_sha256'],
            'video': info, 'table_regions_manually_supplied': bool(rects),
            'frames': frames, 'window_associations': associations,
            'skipped_windows': skipped,
            'counts': {'review_windows': len(expected['review_windows']),
                       'frames_planned': len(frames), 'windows_with_evidence_planned': len(associations),
                       'skipped_or_partial_windows': len(skipped)},
            'requires_manual_review': True, 'hand_boundaries_verified': False,
            'cards_or_actions_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': 'Navigation PNGs only. Requested FFmpeg seek != verified decoded PTS. OCR boundaries are hypotheses; human review required.'}


def export_boundary_visual_evidence(video_path, temporal_json, boundary_json, output_dir,
                                    *, max_frames=60, samples_per_window=3,
                                    regions_json=None):
    video, temporal_path, boundary_path = map(_regular, (video_path, temporal_json, boundary_json))
    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        raise ValueError('Output directory already exists')
    sources = [video, temporal_path, boundary_path]
    if regions_json is not None:
        sources.append(_regular(regions_json))
    hashes = [_sha(path) for path in sources]
    temporal = json.loads(temporal_path.read_text(encoding='utf-8'))
    boundary = json.loads(boundary_path.read_text(encoding='utf-8'))
    regions = json.loads(sources[-1].read_text(encoding='utf-8')) if regions_json is not None else None
    plan = build_boundary_visual_plan(video, temporal, boundary, temporal_sha256=hashes[1],
                                      max_frames=max_frames, samples_per_window=samples_per_window,
                                      table_regions=regions)
    plan['source_boundary_report_sha256'] = hashes[2]
    plan['source_regions_json_sha256'] = hashes[3] if regions_json is not None else None
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_ocr_boundary_', dir=output.parent) as tmp:
        stage = Path(tmp)
        for frame in plan['frames']:
            target = stage / frame['filename']
            cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-ss', str(frame['requested_seek_seconds']), '-i', str(video)]
            rect = frame['region']
            if rect is not None:
                cmd += ['-vf', 'crop={width}:{height}:{x}:{y}'.format(**rect)]
            cmd += ['-frames:v', '1', '-update', '1', '-y', str(target)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=45)
            if not target.is_file() or target.stat().st_size < 100:
                raise ValueError('FFmpeg did not produce a valid navigation PNG')
            frame['sha256'] = _sha(target)
            frame['status'] = 'navigation_png_extracted_not_pts_audited'
        if any(_sha(p) != digest for p, digest in zip(sources, hashes)):
            raise ValueError('Source changed during extraction')
        (stage / 'boundary_visual_evidence.json').write_text(
            json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
            encoding='utf-8')
        # mkdir is exclusive even if another process creates the output meanwhile.
        output.mkdir(exist_ok=False)
        try:
            for item in stage.iterdir():
                os.replace(item, output / item.name)
        except BaseException:
            shutil.rmtree(output)
            raise
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('temporal_ocr_json')
    parser.add_argument('boundary_json')
    parser.add_argument('output_dir')
    parser.add_argument('--regions-json')
    parser.add_argument('--max-frames', type=int, default=60)
    parser.add_argument('--samples-per-window', type=int, default=3)
    args = parser.parse_args(argv)
    report = export_boundary_visual_evidence(
        args.video, args.temporal_ocr_json, args.boundary_json, args.output_dir,
        max_frames=args.max_frames, samples_per_window=args.samples_per_window,
        regions_json=args.regions_json)
    print(json.dumps(report['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
