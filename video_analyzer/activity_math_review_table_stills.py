"""Crop offline math-review navigation stills by declared table regions.

This stage never recognizes cards/actions or approves an equity, EV or clip.
It validates the upstream handoff against its original evidence and verifies
all source image hashes before producing table-specific navigation images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from activity_math_review_frames import build_math_review_frame_plan
from activity_snapshot_chain import canonical_sha256
from table_regions import Region, grid_regions, validate_regions

STATUS = 'unverified_table_navigation_stills_no_math_or_clip_authority'
FRAME_NAME = re.compile(r'frame_[0-9]{4}\.png\Z')


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected regular non-symlink input file')
    return path


def _regions(config, width, height, used_tables):
    if not isinstance(config, dict) or type(config.get('schema_version')) is not int or config['schema_version'] != 1:
        raise ValueError('Invalid region configuration version')
    if config.get('layout') == 'grid':
        if set(config) != {'schema_version', 'layout', 'rows', 'columns'}:
            raise ValueError('Invalid grid configuration')
        rows, cols = config['rows'], config['columns']
        if type(rows) is not int or type(cols) is not int or not 1 <= rows * cols <= 4 or rows <= 0 or cols <= 0:
            raise ValueError('Grid supports one to four tables')
        regions = grid_regions(width, height, rows, cols)
    elif config.get('layout') == 'manual':
        if set(config) != {'schema_version', 'layout', 'regions'} or not isinstance(config['regions'], list):
            raise ValueError('Invalid manual configuration')
        if not 1 <= len(config['regions']) <= 4:
            raise ValueError('Require one to four regions')
        regions = []
        for row in config['regions']:
            if not isinstance(row, dict) or set(row) != {'table_id', 'x', 'y', 'width', 'height'}:
                raise ValueError('Invalid region fields')
            if any(type(v) is not int for v in row.values()) or not 1 <= row['table_id'] <= 4:
                raise ValueError('Region fields must be integers with table IDs 1–4')
            regions.append(Region(**row))
    else:
        raise ValueError('Unknown region layout')
    validate_regions(regions, width, height)
    if {r.table_id for r in regions} != used_tables:
        raise ValueError('Regions must cover exactly the tables in review tasks')
    return sorted(regions, key=lambda r: r.table_id)


def _probe_png(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=width,height', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True, timeout=20)
    streams = json.loads(result.stdout).get('streams', [])
    if len(streams) != 1:
        raise ValueError('Expected one image stream')
    return streams[0]['width'], streams[0]['height']


def _verified_inputs(video, frames_dir, handoff, triage, packet, timeline, region_config):
    video = _regular_file(video)
    frames_dir = Path(frames_dir)
    if frames_dir.is_symlink() or not frames_dir.is_dir():
        raise ValueError('Expected non-symlink frames directory')
    sources = [_regular_file(p) for p in (handoff, triage, packet, timeline, region_config)]
    handoff_data, triage_data, packet_data, timeline_data, config = [
        json.loads(p.read_text(encoding='utf-8')) for p in sources]
    manifest_path = _regular_file(frames_dir / 'math_review_frames.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('frames'), list):
        raise ValueError('Invalid upstream frame manifest')
    if not isinstance(manifest.get('counts'), dict):
        raise ValueError('Invalid upstream frame counts')
    count = manifest['counts'].get('frames_planned')
    if type(count) is not int or not 0 <= count <= 100:
        raise ValueError('Invalid upstream frame count')
    expected = build_math_review_frame_plan(
        video, handoff_data, triage_data, packet_data, timeline_data,
        max_frames=max(1, count))
    if len(manifest['frames']) != len(expected['frames']):
        raise ValueError('Frame manifest differs from verified upstream plan')
    verified_frames = []
    for frame, baseline in zip(manifest['frames'], expected['frames']):
        if not isinstance(frame, dict) or set(frame) != set(baseline):
            raise ValueError('Frame fields differ from upstream plan')
        if not FRAME_NAME.fullmatch(frame['filename']):
            raise ValueError('Invalid frame filename')
        if any(frame[key] != value for key, value in baseline.items() if key != 'sha256'):
            raise ValueError('Frame timestamps or metadata changed')
        sha = frame['sha256']
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise ValueError('Missing or invalid frame SHA-256')
        path = _regular_file(frames_dir / frame['filename'])
        if _sha(path) != sha:
            raise ValueError('Frame SHA-256 mismatch')
        if _probe_png(path) != (expected['video']['width'], expected['video']['height']):
            raise ValueError('Frame dimensions differ from recording')
        verified_frames.append((frame, path))
    baseline_manifest = dict(manifest)
    baseline_manifest['frames'] = [{**frame, 'sha256': None} for frame in manifest['frames']]
    if baseline_manifest != expected:
        raise ValueError('Upstream manifest differs from recomputed evidence')
    used_tables = {r['table_id'] for r in expected['review_tasks']}
    regions = _regions(config, expected['video']['width'], expected['video']['height'], used_tables)
    return expected, manifest, verified_frames, regions, sources, config


def export_math_review_table_stills(video_path, frames_dir, handoff_json, triage_json,
                                    packet_json, timeline_json, regions_json, output_dir):
    """Verify full-frame evidence, crop requested table views, publish atomically."""
    output = Path(output_dir)
    source_dir = Path(frames_dir)
    if (output.exists() or output.is_symlink() or
            output.resolve().is_relative_to(source_dir.resolve())):
        raise ValueError('Require new output outside source frame directory')
    expected, manifest, frames, regions, sources, config = _verified_inputs(
        video_path, frames_dir, handoff_json, triage_json, packet_json, timeline_json, regions_json)
    lookup = {f['filename']: p for f, p in frames}
    region_lookup = {r.table_id: r for r in regions}
    source_hashes = [_sha(p) for p in sources]
    manifest_hash = _sha(source_dir / 'math_review_frames.json')
    pairs = sorted({(task['table_id'], task['frame_filename'])
                    for task in expected['review_tasks'] if task['frame_filename'] is not None})
    output.parent.mkdir(parents=True, exist_ok=True)
    crops = []
    with tempfile.TemporaryDirectory(prefix='.plo_table_stills_', dir=output.parent) as tmp:
        stage = Path(tmp)
        for table_id, filename in pairs:
            region = region_lookup[table_id]
            name = f'table_{table_id:02d}_{filename}'
            target = stage / name
            vf = f'crop={region.width}:{region.height}:{region.x}:{region.y}'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-i', str(lookup[filename]), '-vf', vf,
                            '-frames:v', '1', '-update', '1', '-y', str(target)],
                           check=True, capture_output=True, timeout=40)
            if not target.is_file() or target.stat().st_size < 50:
                raise ValueError('Missing cropped PNG')
            if _probe_png(target) != (region.width, region.height):
                raise ValueError('Incorrect crop dimensions')
            crops.append({'table_id': table_id, 'source_frame_filename': filename,
                          'filename': name, 'sha256': _sha(target),
                          'source_frame_sha256': manifest['frames'][int(filename[6:10])]['sha256'],
                          'region': vars(region),
                          'requested_seek_pts_seconds': next(
                              f['requested_seek_pts_seconds'] for f, _ in frames if f['filename'] == filename),
                          'decoded_frame_pts_seconds': None})
        # Check for source changes while FFmpeg was running.
        for frame, path in frames:
            if _sha(path) != frame['sha256']:
                raise ValueError('Source frame changed during crop')
        for path, prior in zip(sources, source_hashes):
            if _sha(path) != prior:
                raise ValueError('Source JSON changed during crop')
        if _sha(video_path) != expected['recording_sha256']:
            raise ValueError('Recording changed during crop')
        if _sha(source_dir / 'math_review_frames.json') != manifest_hash:
            raise ValueError('Frame manifest changed during crop')
        mapping = {(r['table_id'], r['source_frame_filename']): r['filename'] for r in crops}
        report = {
            'schema_version': 1, 'analysis_status': STATUS,
            'recording_sha256': expected['recording_sha256'],
            'source_full_frame_manifest_sha256': manifest_hash,
            'source_region_config_sha256': canonical_sha256(config),
            'regions': [vars(r) for r in regions],
            'crops': crops,
            'review_tasks': [
                {'table_id': task['table_id'],
                 'hand_id_human_assigned_not_verified': task['hand_id_human_assigned_not_verified'],
                 'observation_index': task['observation_index'],
                 'source_event_sha256': task['source_event_sha256'],
                 'decision_pts_seconds': task['decision_pts_seconds'],
                 'crop_filename': mapping.get((task['table_id'], task['frame_filename']))
                     if task['frame_filename'] else None,
                 'ready_for_equity_or_ev': False,
                 'reviewer_approved_for_manual_clip': False}
                for task in expected['review_tasks']],
            'counts': {'table_crops': len(crops), 'review_tasks': len(expected['review_tasks']),
                       'frames_omitted_by_budget': expected['counts']['frames_omitted_by_budget']},
            'regions_human_confirmed': False,
            'cards_or_actions_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': 'Navigation crops only. Grid/manual coordinates are not table detection; decoded PTS is unknown. No cards, actions, EV, equity, or clip approval.',
        }
        (stage / 'math_review_table_stills.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.replace(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'frames_dir', 'handoff_json', 'triage_json', 'packet_json',
                 'timeline_json', 'regions_json', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    report = export_math_review_table_stills(
        args.video, args.frames_dir, args.handoff_json, args.triage_json,
        args.packet_json, args.timeline_json, args.regions_json, args.output_dir)
    print(json.dumps(report['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
