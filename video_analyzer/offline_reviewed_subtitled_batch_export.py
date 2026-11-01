"""Offline, reviewed-only MP4 clip export with visible explanatory subtitles.

No automatic poker interpretation or real-time assistance. Manifest labels are
self-attested and do NOT certify that a review or equity calculation occurred.
CLI: python offline_reviewed_subtitled_batch_export.py recording.mp4 review.json NEW_DIR
Manifest timestamps are playback-relative seconds, not absolute source PTS.
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

MAX_CLIPS = 12
MAX_CLIP_SECONDS = 180
MAX_JSON_BYTES = 64 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
REVIEW_ID = re.compile(r"[A-Za-z0-9_-]{1,40}\Z")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load_manifest(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_JSON_BYTES, 'invalid review manifest')
    return json.loads(path.read_text(encoding='utf-8'),
                      object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def run_command(argv, *, cwd=None, timeout=90):
    try:
        return subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, check=True, timeout=timeout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'media tool failed: {type(exc).__name__}') from exc


def duration_seconds(video, ffprobe='ffprobe'):
    data = json.loads(run_command([ffprobe, '-v', 'error', '-show_entries',
        'format=duration', '-of', 'json', str(video)], timeout=30).stdout)
    duration = float(data['format']['duration'])
    require(math.isfinite(duration) and 0 < duration <= 4 * 3600,
            'invalid recording duration')
    return duration


def video_dimensions(video, ffprobe='ffprobe'):
    data = json.loads(run_command([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'json', str(video)], timeout=30).stdout)
    stream = data['streams'][0]
    width, height = stream['width'], stream['height']
    require(type(width) is int and type(height) is int and
            2 <= width <= 8192 and 2 <= height <= 8192, 'invalid source dimensions')
    return width, height


def validate_manifest(data, video_hash, duration, dimensions):
    require(type(data) is dict and set(data) ==
            {'schema_version', 'recording_sha256', 'time_basis', 'clips'} and
            type(data['schema_version']) is int and data['schema_version'] == 1 and
            data['time_basis'] == 'playback_seconds' and
            type(data['recording_sha256']) is str and
            HEX.fullmatch(data['recording_sha256']) and
            data['recording_sha256'] == video_hash, 'manifest/source hash mismatch')
    clips = data['clips']
    require(type(clips) is list and 1 <= len(clips) <= MAX_CLIPS,
            'invalid clip count')
    seen = set()
    for item in clips:
        require(type(item) is dict and set(item) ==
                {'review_id', 'table_id', 'start_seconds', 'end_seconds',
                 'explanation', 'human_reviewed', 'crop'}, 'invalid clip fields')
        review_id, table, start, end, explanation = (
            item[k] for k in ('review_id', 'table_id', 'start_seconds',
                              'end_seconds', 'explanation'))
        require(type(review_id) is str and REVIEW_ID.fullmatch(review_id) and
                review_id not in seen, 'invalid/duplicate review ID')
        seen.add(review_id)
        require(type(table) is int and 1 <= table <= 4 and
                type(start) in (int, float) and type(end) in (int, float) and
                math.isfinite(start) and math.isfinite(end) and
                0 <= start < end <= duration + 0.001 and
                end - start <= MAX_CLIP_SECONDS, 'invalid clip interval')
        crop = item['crop']
        require(type(crop) is dict and set(crop) == {'x', 'y', 'width', 'height'} and
                all(type(v) is int and v >= 0 for v in crop.values()),
                'invalid table crop')
        x, y, w, h = (crop[k] for k in ('x', 'y', 'width', 'height'))
        require(w >= 2 and h >= 2 and all(v % 2 == 0 for v in (x, y, w, h)) and
                x + w <= dimensions[0] and y + h <= dimensions[1],
                'table crop outside video')
        require(item['human_reviewed'] is True, 'human review required')
        require(type(explanation) is str and 1 <= len(explanation.strip()) <= 200 and
                '\n' not in explanation and '\r' not in explanation and
                not any(ord(c) < 32 or c in '<>{}' for c in explanation),
                'invalid subtitle text')
    return clips


def srt_time(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    sec, millis = divmod(millis, 1000)
    return f'{hours:02d}:{minutes:02d}:{sec:02d},{millis:03d}'


def export(recording_path, review_path, output_dir, *, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    video, review, output = map(Path, (recording_path, review_path, output_dir))
    require(video.is_file() and not video.is_symlink() and
            video.stat().st_size > 0 and review.is_file() and not review.is_symlink() and
            video.resolve() != review.resolve(), 'unsafe input files')
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(not p.resolve().is_relative_to(output.resolve()) for p in (video, review)),
            'output must be a new, disjoint directory')
    # FFmpeg runs with cwd=stage to resolve subtitles; keep source path absolute.
    video = video.resolve()
    original_hash, review_hash = sha256(video), sha256(review)
    source_duration = duration_seconds(video, ffprobe)
    clips = validate_manifest(load_manifest(review), original_hash, source_duration,
                              video_dimensions(video, ffprobe))
    with tempfile.TemporaryDirectory(prefix='.plo_reviewed_clips_', dir=output.parent) as temp:
        stage = Path(temp) / 'published'
        stage.mkdir()
        records = []
        for index, item in enumerate(clips):
            require(sha256(video) == original_hash and sha256(review) == review_hash,
                    'source changed during clip export')
            stem = f'clip_{index:02d}_table_{item["table_id"]}_{item["review_id"]}'
            srt = stage / (stem + '.srt')
            mp4 = stage / (stem + '.mp4')
            requested = item['end_seconds'] - item['start_seconds']
            srt.write_text('1\n' + srt_time(0) + ' --> ' +
                           srt_time(requested) + '\n' + item['explanation'].strip() +
                           '\n', encoding='utf-8')
            # Relative subtitle path avoids injecting user text or paths into filters.
            crop = item['crop']
            crop_filter = 'crop={width}:{height}:{x}:{y}'.format(**crop)
            run_command([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-ss', str(item['start_seconds']), '-i', str(video),
                '-t', str(requested), '-map', '0:v:0', '-map', '0:a:0?',
                '-vf', f'{crop_filter},subtitles={srt.name}', '-c:v', 'libx264',
                '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac',
                '-movflags', '+faststart', str(mp4)], cwd=stage, timeout=180)
            actual = duration_seconds(mp4, ffprobe)
            require(mp4.is_file() and mp4.stat().st_size > 0 and
                    abs(actual - requested) <= 0.6,
                    'exported clip duration mismatch')
            records.append({'review_id': item['review_id'], 'table_id': item['table_id'],
                'start_seconds': item['start_seconds'], 'end_seconds': item['end_seconds'],
                'explanation': item['explanation'].strip(), 'crop': crop, 'mp4': mp4.name,
                'mp4_sha256': sha256(mp4), 'srt': srt.name,
                'srt_sha256': sha256(srt), 'output_duration_seconds': actual})
        report = {'schema_version': 1, 'status': 'offline_human_reviewed_clips_exported',
                  'recording_sha256': original_hash, 'review_manifest_sha256': review_hash,
                  'time_basis': 'playback_seconds',
                  'clips': records, 'review_authenticity_verified': False,
                  'equity_or_ev_verified': False, 'poker_accuracy_verified': False,
                  'warning': 'Review flags and explanations are supplied by the user, not independently authenticated.'}
        (stage / 'export_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        require(sha256(video) == original_hash and sha256(review) == review_hash and
                not output.exists() and not output.is_symlink(),
                'input changed or output appeared before publication')
        os.rename(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('review_manifest')
    parser.add_argument('new_output_directory')
    args = parser.parse_args(argv)
    report = export(args.recording, args.review_manifest, args.new_output_directory)
    print(json.dumps({'status': report['status'], 'clips': len(report['clips'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
