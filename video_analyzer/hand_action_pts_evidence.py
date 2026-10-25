"""Offline, bounded FFmpeg evidence for *human-reviewed* hand annotations.

Revalidates the navigation/review worksheet and video hash. A second independent
FFmpeg decode checks PNG identity and filtergraph PTS. Even a matching frame
DOES NOT validate card/action content, a hand, equity, EV or strategy.
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

from boundary_hand_draft import _read, build_template, validate_review
from activity_math_review_pts_audit import _parse_decoded_pts
from activity_ocr_boundary_visual_evidence import _regions
from video_validator import validate_recording

MAX_FRAMES = 120
MAX_SECONDS = 3600
PTS_TOLERANCE = 0.25
FALSE_FLAGS = ('hand_boundaries_verified', 'cards_or_actions_verified',
               'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
               'strategic_error_established')


def _file(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('Expected regular non-symlink input')
    return p


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _validated_review(navigation, navigation_sha, review):
    template = build_template(navigation, navigation_sha)
    if (not isinstance(review, dict)
            or review.get('analysis_status') != 'manual_hand_history_review_unverified_no_math'
            or not isinstance(review.get('entries'), list)):
        raise ValueError('Invalid hand review')
    expected = validate_review(navigation, navigation_sha,
                               {**template, 'entries': review['entries']})
    if expected != review:
        raise ValueError('Reviewed hand report differs from revalidated source')
    return expected


def build_plan(video, navigation, navigation_sha, review, *, max_frames=60,
               table_regions=None):
    """Create auditable frame requests; never treat requests as decoded PTS."""
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError('Invalid frame budget')
    _validated_review(navigation, navigation_sha, review)
    info = validate_recording(_file(video))
    digest = _sha(video)
    if digest != navigation['recording_sha256'] or digest != review['recording_sha256']:
        raise ValueError('Recording SHA-256 mismatch')
    rects = _regions(table_regions, info['width'], info['height'])
    tables = {e['table_id'] for e in review['entries']}
    if len(tables) > 1 and any(t not in rects for t in tables):
        raise ValueError('Multi-table recordings require a region for every reviewed table')
    requests = []
    for entry in review['entries']:
        for name, field in entry['fields'].items():
            if field['source_kind'] == 'manual_video_review' and field['human_confirmed']:
                requests.append((entry, 'field', name, field['source_pts_seconds']))
        for index, action in enumerate(entry['actions']):
            if action['source_kind'] == 'manual_video_review' and action['human_confirmed']:
                requests.append((entry, 'action', index, action['timestamp_seconds']))
    requests.sort(key=lambda row: (row[0]['table_id'], row[3], row[0]['entry_id'],
                                   row[1], str(row[2])))
    frames, associations, skipped, keys = [], [], [], {}
    for entry, kind, item, pts in requests:
        # Revalidated annotation timestamps are finite, but a video can be shorter.
        if (type(pts) not in (int, float) or not math.isfinite(pts)
                or not 0 <= pts < min(info['duration_seconds'], MAX_SECONDS)):
            skipped.append({'entry_id': entry['entry_id'], 'kind': kind,
                            'item': item, 'reason': 'timestamp_outside_recording'})
            continue
        seek = round(pts, 6)
        key = (entry['table_id'], seek)
        if key not in keys:
            if len(frames) >= max_frames:
                skipped.append({'entry_id': entry['entry_id'], 'kind': kind,
                                'item': item, 'reason': 'frame_budget_exceeded'})
                continue
            index = len(frames)
            keys[key] = index
            frames.append({'frame_id': index, 'table_id': entry['table_id'],
                           'requested_seek_seconds': seek,
                           'region': rects.get(entry['table_id']),
                           'filename': f'action_table_{entry["table_id"]:02d}_{index:04d}.png'})
        associations.append({'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
                             'kind': kind, 'item': item, 'frame_id': keys[key],
                             'requires_manual_review': True})
    return {'schema_version': 1, 'analysis_status': 'manual_action_frame_plan_no_math',
            'recording_sha256': digest, 'source_navigation_sha256': navigation_sha,
            'video': info, 'table_regions_manually_supplied': bool(rects),
            'frames': frames, 'associations': associations, 'skipped': skipped,
            'counts': {'human_confirmed_requests': len(requests),
                       'frames_planned': len(frames), 'requests_linked': len(associations),
                       'requests_skipped': len(skipped)},
            'requires_manual_review': True, **{key: False for key in FALSE_FLAGS}}


def _decode(video, seek, rect, output):
    filters = ['showinfo']
    if rect is not None:
        filters.append('crop={width}:{height}:{x}:{y}'.format(**rect))
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info', '-copyts',
           '-ss', str(seek), '-i', str(video), '-vf', ','.join(filters),
           '-frames:v', '1', '-update', '1', '-y', str(output)]
    run = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
    ticks, seconds, timebase = _parse_decoded_pts(run.stderr)
    if not output.is_file() or not 100 < output.stat().st_size <= 20_000_000:
        raise ValueError('Invalid decoded PNG')
    with output.open('rb') as f:
        if f.read(8) != bytes.fromhex('89504e470d0a1a0a'):
            raise ValueError('Decoded image is not PNG')
    return {'ticks': ticks, 'seconds': seconds, 'timebase': timebase, 'sha256': _sha(output)}


def export(video_path, navigation_path, review_path, output_dir, *, regions_json=None,
           max_frames=60):
    """Publish new immutable PNGs and a report after a second PTS-byte audit."""
    video, nav_path, review_path = map(_file, (video_path, navigation_path, review_path))
    sources = [video, nav_path, review_path]
    if regions_json is not None:
        sources.append(_file(regions_json))
    if len({p.resolve() for p in sources}) != len(sources):
        raise ValueError('Input paths must be distinct')
    hashes = [_sha(p) for p in sources]
    nav, nav_sha = _read(nav_path)
    review, _ = _read(review_path)
    regions = _read(sources[-1])[0] if regions_json is not None else None
    plan = build_plan(video, nav, nav_sha, review, max_frames=max_frames,
                      table_regions=regions)
    output = Path(output_dir)
    if (output.exists() or output.is_symlink()
            or any(p.resolve().is_relative_to(output.resolve()) for p in sources)):
        raise ValueError('Output must be new and outside source files')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_action_pts_', dir=output.parent) as tmp:
        stage = Path(tmp)
        rows = []
        for frame in plan['frames']:
            png = stage / frame['filename']
            original = _decode(video, frame['requested_seek_seconds'], frame['region'], png)
            replay = _decode(video, frame['requested_seek_seconds'], frame['region'],
                             stage / ('replay_' + frame['filename']))
            matched = (original['sha256'] == replay['sha256']
                       and original['ticks'] == replay['ticks']
                       and original['timebase'] == replay['timebase']
                       and original['seconds'] == replay['seconds'])
            delta = original['seconds'] - frame['requested_seek_seconds'] if matched else None
            close = matched and abs(delta) <= PTS_TOLERANCE
            rows.append({**frame, 'png_sha256': original['sha256'],
                         'redecoded_png_sha256': replay['sha256'],
                         'pts_byte_matched': matched,
                         'decoded_pts_seconds': original['seconds'] if matched else None,
                         'decoded_pts_ticks': original['ticks'] if matched else None,
                         'decoded_pts_time_base': original['timebase'] if matched else None,
                         'requested_to_decoded_delta_seconds': delta,
                         'within_requested_pts_tolerance': close,
                         'status': ('audited_near_requested_pts_not_content_verified' if close
                                    else 'no_usable_nearby_audited_frame')})
            (stage / ('replay_' + frame['filename'])).unlink()
        if any(_sha(p) != digest for p, digest in zip(sources, hashes)):
            raise ValueError('Input changed during extraction')
        report = {**plan, 'analysis_status': 'manual_action_pts_audit_no_content_validation',
                  'source_review_sha256': hashes[2],
                  'source_regions_json_sha256': hashes[3] if regions_json is not None else None,
                  'frames': rows,
                  'counts': {**plan['counts'],
                             'pts_byte_matched': sum(x['pts_byte_matched'] for x in rows),
                             'near_requested_pts': sum(x['within_requested_pts_tolerance'] for x in rows)},
                  'timestamp_semantics': 'ffmpeg_filtergraph_pts_not_wall_clock',
                  'warning': ('PNG byte identity and decoded PTS do not establish that a '
                              'human annotation, hand boundary, card or action is correct.')}
        (stage / 'action_pts_evidence.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
            encoding='utf-8')
        output.mkdir(exist_ok=False)
        try:
            for item in stage.iterdir():
                os.replace(item, output / item.name)
        except BaseException:
            shutil.rmtree(output)
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('navigation')
    parser.add_argument('review')
    parser.add_argument('output_dir')
    parser.add_argument('--regions-json')
    parser.add_argument('--max-frames', type=int, default=60)
    args = parser.parse_args(argv)
    report = export(args.video, args.navigation, args.review, args.output_dir,
                    regions_json=args.regions_json, max_frames=args.max_frames)
    print(json.dumps(report['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
