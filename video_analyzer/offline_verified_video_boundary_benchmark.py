"""Evaluate offline hand-boundary proposals only after verifying the actual video.

CLI: python offline_verified_video_boundary_benchmark.py VIDEO.mp4 PROPOSALS.json LABELS.json NEW_REPORT.json

This is a provenance-checked *evaluation* tool, not a hand detector. The video
is never used for real-time poker decisions, and label correctness remains
unverified even when the recording hash matches its bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import offline_hand_boundary_benchmark as boundary

MAX_VIDEO_BYTES = 20 * 1024**3
MAX_VIDEO_SECONDS = 4 * 60 * 60
SUPPORTED_EXTENSIONS = {'.mp4', '.webm'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_file(path, *, video=False):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'file missing or symlink')
    size = path.stat().st_size
    require(0 < size <= (MAX_VIDEO_BYTES if video else boundary.MAX_BYTES),
            'invalid file size')
    if video:
        require(path.suffix.lower() in SUPPORTED_EXTENSIONS, 'unsupported video extension')
    return path


def finite_number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'invalid {label}') from None
    require(math.isfinite(result), f'invalid {label}')
    return result


def probe_video(path, *, ffprobe='ffprobe'):
    # Absolute local path and a file-only protocol whitelist prevent URL input.
    command = [ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
               '-show_entries', 'format=duration,start_time:stream=index,codec_type,start_time,duration',
               '-of', 'json', '-i', str(Path(path).resolve())]
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('ffprobe unavailable or timed out') from exc
    require(process.returncode == 0 and len(process.stdout) < 200_000,
            'ffprobe rejected video')
    try:
        result = json.loads(process.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError('invalid ffprobe JSON') from exc
    require(type(result) is dict and type(result.get('streams')) is list,
            'missing stream metadata')
    video_streams = [s for s in result['streams'] if s.get('codec_type') == 'video']
    require(len(video_streams) == 1, 'requires exactly one video stream')
    fmt = result.get('format', {})
    require(type(fmt) is dict, 'invalid format metadata')
    duration = finite_number(fmt.get('duration'), 'video duration')
    require(0.05 <= duration <= MAX_VIDEO_SECONDS, 'video duration outside limits')
    stream = video_streams[0]
    start = finite_number(stream.get('start_time', fmt.get('start_time', '0')),
                          'video stream start time')
    require(-60 <= start <= MAX_VIDEO_SECONDS, 'invalid stream start time')
    return {'duration_seconds': duration, 'stream_start_pts_seconds': start,
            'video_stream_index': stream.get('index'),
            'stream_count': len(result['streams'])}


def verify_bounds(report, duration, origin, *, slack=0.02):
    # All interval endpoints must lie within the decoded recording's timeline.
    for name, rows in [('proposals', report['boundaries'])]:
        for row in rows:
            require(origin - slack <= row['start_seconds'] and
                    row['end_seconds'] <= origin + duration + slack,
                    f'{name} interval outside recording')


def verify_labels(labels, duration, origin, *, slack=0.02):
    for row in labels['hands']:
        require(origin - slack <= row['start_seconds'] and
                row['end_seconds'] <= origin + duration + slack,
                'human label interval outside recording')


def run(video_path, proposals_path, labels_path, output_path, *,
        tolerance_seconds=0.5, timeline_basis='video-relative', ffprobe='ffprobe'):
    require(timeline_basis in ('video-relative', 'source-pts'), 'invalid timeline basis')
    video = safe_file(video_path, video=True)
    proposals = safe_file(proposals_path)
    labels = safe_file(labels_path)
    output = Path(output_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(),
            'output must be a new file in an existing directory')
    paths = [video, proposals, labels, output]
    require(len({str(p.resolve()) for p in paths}) == len(paths), 'colliding paths')

    before = [file_hash(p) for p in (video, proposals, labels)]
    p = boundary.load(proposals)
    g = boundary.load(labels)
    require(p.get('recording_sha256') == before[0] and
            g.get('recording_sha256') == before[0],
            'manifest recording hashes do not match actual video')
    meta = probe_video(video, ffprobe=ffprobe)
    origin = 0.0 if timeline_basis == 'video-relative' else meta['stream_start_pts_seconds']
    # Validate the original strict schemas before inspecting their intervals.
    report = boundary.evaluate(p, g, tolerance_seconds=tolerance_seconds)
    verify_bounds(p, meta['duration_seconds'], origin)
    verify_labels(g, meta['duration_seconds'], origin)
    require([file_hash(x) for x in (video, proposals, labels)] == before,
            'source files changed during evaluation')

    report.update({
        'status': 'offline_boundary_agreement_with_recording_hash_verified',
        'recording_sha256_verified_against_bytes': before[0],
        'recording_bytes': video.stat().st_size,
        'recording_metadata_ffprobe': meta,
        'timestamp_basis': timeline_basis,
        'timestamp_origin_seconds': origin,
        'recording_hash_verified': True,
        'recording_is_local_video_ffprobe_verified': True,
        'human_labels_verified_against_video': False,
        'visual_hand_boundary_accuracy_verified': False,
        'ready_for_equity_or_ev': False,
        'hands_reconstructed': False,
        'source_proposals_sha256': before[1],
        'source_human_labels_sha256': before[2],
        'limitations': report['limitations'] + [
            'Recording bytes and declared hash agree, but human annotations have not been visually authenticated.',
            'FFprobe duration and stream timestamps are metadata, not frame-by-frame proof of hand boundaries.',
            'This evaluator cannot authorize reconstructed hands, equity, EV, or clip decisions.']})
    with tempfile.TemporaryDirectory(prefix='.plo_verified_boundary_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'report.json'
        staged.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                     allow_nan=False) + '\n', encoding='utf-8')
        # Atomic create-only publishing, even under a concurrent writer.
        require([file_hash(x) for x in (video, proposals, labels)] == before,
                'source files changed before publishing')
        os.link(staged, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('proposals_json')
    parser.add_argument('human_labels_json')
    parser.add_argument('new_report_json')
    parser.add_argument('--tolerance-seconds', type=float, default=0.5)
    parser.add_argument('--timeline-basis', choices=('video-relative', 'source-pts'),
                        default='video-relative')
    args = parser.parse_args(argv)
    report = run(args.video, args.proposals_json, args.human_labels_json,
                 args.new_report_json, tolerance_seconds=args.tolerance_seconds,
                 timeline_basis=args.timeline_basis)
    print(json.dumps({'matched': report['summary']['matched'],
                      'recording_hash_verified': True,
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
