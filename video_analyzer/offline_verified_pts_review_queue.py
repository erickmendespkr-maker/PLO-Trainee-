"""Offline hand/OCR queue with FFmpeg-measured first-video-frame PTS origin.

This is a timestamp provenance check, not proof of poker observations.
Source regions, hand intervals and OCR remain human-declared/unverified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

import offline_hand_ocr_review_queue as queue

PTS_RE = re.compile(r'\bpts_time:\s*(-?\d+(?:\.\d+)?)')
MAX_STDERR = 256 * 1024


def _run(command, timeout):
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=timeout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg/FFprobe source PTS verification failed') from exc


def measure_origin(video):
    """Use the first *decoded video* PTS, not a user-supplied offset."""
    video = Path(video)
    queue.check(video.is_file() and not video.is_symlink() and
                video.suffix.lower() in ('.mp4', '.webm'), 'unsafe recording')
    probe = _run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                  '-show_entries', 'stream=start_time:format=duration',
                  '-of', 'json', str(video)], 30)
    queue.check(len(probe.stdout) <= 65536, 'oversized FFprobe output')
    try:
        info = json.loads(probe.stdout)
        streams = info['streams']
        duration = float(info['format']['duration'])
        stream_start = float(streams[0]['start_time'])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError('missing or ambiguous video PTS metadata') from exc
    queue.check(len(streams) == 1 and all(math.isfinite(x) for x in
                (duration, stream_start)) and 0 < duration <= 3600 and
                abs(stream_start) <= 86400, 'invalid video PTS metadata')
    frame = _run(['ffmpeg', '-hide_banner', '-nostdin', '-noautorotate',
                  '-copyts', '-i', str(video), '-map', '0:v:0', '-an', '-sn', '-dn',
                  '-vf', 'showinfo', '-frames:v', '1', '-f', 'null', '-'], 60)
    queue.check(len(frame.stderr) <= MAX_STDERR, 'oversized FFmpeg output')
    pts = []
    for line in frame.stderr.decode('utf-8', 'replace').splitlines():
        if 'Parsed_showinfo' in line and 'pts_time:' in line:
            match = PTS_RE.search(line)
            if match:
                pts.append(float(match.group(1)))
    queue.check(len(pts) == 1 and math.isfinite(pts[0]) and
                abs(pts[0] - stream_start) <= .5,
                'first decoded video PTS disagrees with stream start')
    return {'first_decoded_video_frame_pts_seconds': pts[0],
            'ffprobe_video_stream_start_seconds': stream_start,
            'ffprobe_recording_duration_seconds': duration,
            'origin_method': 'first_decoded_video_frame_showinfo_pts_time',
            'origin_disagreement_tolerance_seconds': .5}


def build(video, bundle, proposals, boundaries):
    video = Path(video)
    before = queue.digest(video)
    evidence = measure_origin(video)
    origin = evidence['first_decoded_video_frame_pts_seconds']
    result = queue.build(video, bundle, proposals, boundaries,
                         source_pts_origin=origin)
    source = queue.load(Path(bundle) / 'region_samples.json')
    duration = evidence['ffprobe_recording_duration_seconds']
    queue.check(all(origin - .001 <= s['decoded_source_pts_seconds'] <
                    origin + duration + .5 for s in source['samples']),
                'sample PTS outside measured video timeline')
    if 'recording_duration_seconds' in source:
        reported = source['recording_duration_seconds']
        queue.check(queue.number(reported) and abs(reported - duration) <= .5,
                    'source manifest duration disagrees with FFprobe')
    queue.check(queue.digest(video) == before, 'video changed during PTS verification')
    result['source_pts_origin_seconds_verified_from_decoded_video'] = origin
    result['pts_origin_evidence'] = evidence
    result['source_pts_origin_seconds_supplied_unverified'] = None
    result['timestamp_conversion'] = 'playback_seconds = decoded_source_pts_seconds - verified_first_video_frame_pts'
    result['warning'] = ('FFmpeg-measured PTS origin only; OCR and human hand boundaries '
                         'remain unverified. No poker facts, equity, EV or automatic clips.')
    return result


def run(video, bundle, proposals, boundaries, output):
    output = Path(output)
    queue.check(output.parent.is_dir() and not output.parent.is_symlink() and
                not output.exists() and not output.is_symlink() and
                output.suffix.lower() == '.json' and
                all(not output.resolve().is_relative_to(Path(p).resolve())
                    for p in (video, bundle, proposals, boundaries)),
                'output must be new and disjoint')
    result = build(video, bundle, proposals, boundaries)
    with tempfile.TemporaryDirectory(prefix='.plo_verified_pts_', dir=output.parent) as temp:
        staged = Path(temp) / 'result.json'
        staged.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                     allow_nan=False) + '\n', encoding='utf-8')
        os.link(staged, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('recording', 'region_bundle', 'ocr_proposals', 'human_boundaries',
                'new_output_json'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    report = run(args.recording, args.region_bundle, args.ocr_proposals,
                 args.human_boundaries, args.new_output_json)
    print(json.dumps({'status': report['status'],
                      'measured_pts_origin': report['source_pts_origin_seconds_verified_from_decoded_video'],
                      'observations_assigned': report['observations_assigned']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
