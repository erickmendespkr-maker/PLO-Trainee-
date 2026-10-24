"""Export full-frame FFmpeg navigation stills for *unverified* math-review tasks.

Offline only. Recomputes the handoff from its original sources, verifies the
recording SHA-256, and labels seek times as requested, not decoded PTS. Images
are navigation evidence, never poker recognition or authorization for clips/EV.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from activity_math_review_handoff import build_math_review_handoff
from activity_snapshot_chain import canonical_sha256
from video_validator import validate_recording

STATUS = 'unverified_full_frame_navigation_stills_no_math_or_clip_authority'


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sources(video, handoff, triage, packet, timeline, max_frames):
    if type(max_frames) is not int or not 1 <= max_frames <= 100:
        raise ValueError('Invalid frame budget')
    if any(not isinstance(x, dict) for x in (handoff, triage, packet, timeline)):
        raise ValueError('Expected JSON objects')
    window = handoff.get('preview_window_seconds')
    if not isinstance(window, dict) or set(window) != {'before', 'after'}:
        raise ValueError('Invalid review window')
    # Recompute every protected row, including PTS, hashes, blockers and flags.
    expected = build_math_review_handoff(
        triage, packet, timeline,
        expected_triage_sha256=handoff.get('source_triage_sha256'),
        expected_packet_sha256=handoff.get('source_hand_review_packet_sha256'),
        expected_timeline_sha256=handoff.get('source_reviewed_timeline_sha256'),
        seconds_before=window['before'], seconds_after=window['after'])
    if expected != handoff:
        raise ValueError('Review handoff differs from recomputed evidence')
    if video.is_symlink() or not video.is_file():
        raise ValueError('Recording must be a regular non-symlink file')
    info = validate_recording(video)
    video_hash = _sha(video)
    if timeline['recording_sha256'] != video_hash or handoff['recording_sha256'] != video_hash:
        raise ValueError('Recording SHA-256 mismatch')
    tasks = handoff['review_tasks']
    times = []
    for row in tasks:
        pts = row['decision_pts_seconds']
        if (type(pts) not in (int, float) or not math.isfinite(pts)
                or not 0 <= pts < info['duration_seconds']):
            raise ValueError('Decision PTS outside recording')
        if pts not in times:
            times.append(pts)
    times.sort()
    return info, video_hash, times[:max_frames], len(times) - min(len(times), max_frames)


def build_math_review_frame_plan(video_path, handoff, triage, packet, timeline, *, max_frames=40):
    """Return a deterministic, unapproved plan; no frames are extracted."""
    video = Path(video_path)
    info, video_hash, times, omitted = _validate_sources(
        video, handoff, triage, packet, timeline, max_frames)
    indices = {pts: i for i, pts in enumerate(times)}
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'recording_sha256': video_hash,
        'source_handoff_sha256': canonical_sha256(handoff),
        'source_triage_sha256': canonical_sha256(triage),
        'source_packet_sha256': canonical_sha256(packet),
        'source_timeline_sha256': canonical_sha256(timeline),
        'video': info,
        'frames': [{'filename': f'frame_{i:04d}.png', 'requested_seek_pts_seconds': pts,
                    'decoded_frame_pts_seconds': None, 'sha256': None,
                    'full_frame_not_table_crop': True}
                   for i, pts in enumerate(times)],
        'review_tasks': [
            {'table_id': row['table_id'],
             'hand_id_human_assigned_not_verified': row['hand_id_human_assigned_not_verified'],
             'observation_index': row['observation_index'],
             'decision_pts_seconds': row['decision_pts_seconds'],
             'frame_filename': f'frame_{indices[row["decision_pts_seconds"]]:04d}.png'
                               if row['decision_pts_seconds'] in indices else None,
             'frame_available_in_budget': row['decision_pts_seconds'] in indices,
             'source_event_sha256': row['source_event_sha256'],
             'reviewer_approved_for_manual_clip': False,
             'ready_for_equity_or_ev': False}
            for row in handoff['review_tasks']],
        'counts': {'unique_requested_pts': len(times) + omitted,
                   'frames_planned': len(times), 'frames_omitted_by_budget': omitted,
                   'review_tasks': len(handoff['review_tasks'])},
        'source_visual_content_verified': False,
        'regions_human_confirmed': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('FFmpeg seek timestamps are requests, NOT measured decoded frame PTS. '
                    'Full-frame navigation only; no cards/actions authenticated, no hand '
                    'boundaries, mathematical approval, automatic ranking or clip export.'),
    }


def export_math_review_frames(video_path, handoff_json, triage_json, packet_json,
                              timeline_json, output_dir, *, max_frames=40):
    paths = [Path(p) for p in (video_path, handoff_json, triage_json, packet_json, timeline_json)]
    output = Path(output_dir)
    if (output.exists() or output.is_symlink()
            or any(p.is_symlink() or not p.is_file() for p in paths)
            or output.resolve() in {p.resolve() for p in paths}):
        raise ValueError('Require regular source files and a new output directory')
    handoff, triage, packet, timeline = [json.loads(p.read_text(encoding='utf-8'))
                                         for p in paths[1:]]
    plan = build_math_review_frame_plan(paths[0], handoff, triage, packet, timeline,
                                        max_frames=max_frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_review_frames_', dir=output.parent) as tmp:
        stage = Path(tmp)
        for frame in plan['frames']:
            target = stage / frame['filename']
            cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-ss', str(frame['requested_seek_pts_seconds']), '-i', str(paths[0]),
                   '-frames:v', '1', '-update', '1', '-y', str(target)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            if not target.is_file() or target.stat().st_size < 100:
                raise ValueError('FFmpeg did not produce a valid navigation still')
            frame['sha256'] = _sha(target)
        if _sha(paths[0]) != plan['recording_sha256']:
            raise ValueError('Recording changed while decoding')
        (stage / 'math_review_frames.json').write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        # Publish only when every requested frame and hash is complete.
        os.replace(stage, output)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('video', 'handoff_json', 'triage_json', 'packet_json', 'timeline_json', 'output_dir'):
        parser.add_argument(arg)
    parser.add_argument('--max-frames', type=int, default=40)
    args = parser.parse_args(argv)
    result = export_math_review_frames(args.video, args.handoff_json, args.triage_json,
                                       args.packet_json, args.timeline_json, args.output_dir,
                                       max_frames=args.max_frames)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
