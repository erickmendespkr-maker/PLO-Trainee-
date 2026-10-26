"""Export human-selected, source-bound MP4 review clips from recorded sessions.

No live capture, inferred hand boundaries, automatic strategic verdicts, or
video-verified equity claims. FFprobe validates the container timeline, NOT
hand/action PTS. FFmpeg embeds the human explanation as a subtitle track.
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

SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_JSON = 32_768
MAX_SECONDS = 3_900
MAX_CLIP_SECONDS = 180


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _pairs(items):
    result = {}
    for k, v in items:
        require(k not in result, 'Duplicate JSON key')
        result[k] = v
    return result


def read_selection(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON,
            'Unsafe or oversized selection')
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON, 'Oversized selection')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def validate_selection(sel):
    required = {'schema_version', 'recording_sha256', 'table_id', 'start_seconds',
                'end_seconds', 'human_selected', 'explanation', 'reviewer_confidence',
                'crop'}
    require(type(sel) is dict and set(sel) == required and
            type(sel['schema_version']) is int and sel['schema_version'] == 1,
            'Invalid selection schema')
    require(type(sel['recording_sha256']) is str and SHA.fullmatch(sel['recording_sha256']),
            'Invalid recording digest')
    require(type(sel['table_id']) is int and 1 <= sel['table_id'] <= 4 and
            sel['human_selected'] is True, 'Manual table selection required')
    start, end = sel['start_seconds'], sel['end_seconds']
    require(finite(start) and finite(end) and 0 <= start < end <= MAX_SECONDS and
            end - start <= MAX_CLIP_SECONDS, 'Invalid clip interval')
    require(finite(sel['reviewer_confidence']) and 0 <= sel['reviewer_confidence'] <= 1,
            'Invalid subjective confidence')
    note = sel['explanation']
    require(type(note) is str and 1 <= len(note.strip()) <= 500 and
            all(ord(c) >= 32 or c == '\n' for c in note), 'Invalid human explanation')
    crop = sel['crop']
    if crop is not None:
        require(type(crop) is dict and set(crop) == {'x', 'y', 'width', 'height'} and
                all(type(v) is int and v >= 0 for v in crop.values()) and
                crop['width'] >= 32 and crop['height'] >= 32 and
                all(v % 2 == 0 for v in crop.values()), 'Invalid even crop')
    return sel


def _run(args, timeout=90):
    try:
        return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise ValueError(f'Media tool failed: {type(e).__name__}') from e


def probe(source):
    raw = _run(['ffprobe', '-v', 'error', '-show_entries',
                'format=duration:stream=index,codec_type,width,height,duration',
                '-of', 'json', str(source)]).stdout
    meta = json.loads(raw)
    videos = [s for s in meta.get('streams', []) if s.get('codec_type') == 'video']
    require(len(videos) == 1, 'Exactly one video stream required')
    stream = videos[0]
    require(type(stream.get('width')) is int and type(stream.get('height')) is int,
            'Unknown video geometry')
    duration = stream.get('duration') or meta.get('format', {}).get('duration')
    try:
        duration = float(duration)
    except (TypeError, ValueError) as e:
        raise ValueError('Unknown duration') from e
    require(math.isfinite(duration) and 0 < duration <= MAX_SECONDS,
            'Unsupported recording duration')
    return {'duration_seconds': duration, 'width': stream['width'],
            'height': stream['height']}


def video_stream_timing(path):
    """Read the exported video stream timeline, not container/subtitle duration.

    This is stream metadata, not a decoded-frame or visual-identity check.
    """
    raw = _run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=start_time,duration', '-of', 'json',
                str(path)], timeout=20).stdout
    require(0 < len(raw) < 8192, 'Invalid video stream timing metadata')
    try:
        streams = json.loads(raw)['streams']
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Unknown video stream timing') from exc
    require(type(streams) is list and len(streams) == 1,
            'Ambiguous video stream timing')
    try:
        start = float(streams[0]['start_time'])
        duration = float(streams[0]['duration'])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError('Unknown video stream timing') from exc
    require(math.isfinite(start) and math.isfinite(duration) and duration > 0,
            'Invalid video stream timing')
    return {'start_seconds': start, 'duration_seconds': duration}



def audio_stream_timing(path):
    """Observe optional exported audio stream timing (not waveform synchronization)."""
    raw = _run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                '-show_entries', 'stream=start_time,duration', '-of', 'json',
                str(path)], timeout=20).stdout
    require(0 < len(raw) < 8192, 'Invalid audio stream timing metadata')
    try:
        streams = json.loads(raw)['streams']
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Unknown audio stream timing') from exc
    require(type(streams) is list and len(streams) <= 1,
            'Ambiguous audio stream timing')
    if not streams:
        return None
    try:
        start = float(streams[0]['start_time'])
        duration = float(streams[0]['duration'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Unknown audio stream timing') from exc
    require(math.isfinite(start) and math.isfinite(duration) and duration > 0,
            'Invalid audio stream timing')
    return {'start_seconds': start, 'duration_seconds': duration}


def _srt_time(seconds):
    millis = round(seconds * 1000)
    h, millis = divmod(millis, 3_600_000)
    m, millis = divmod(millis, 60_000)
    s, millis = divmod(millis, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{millis:03d}'


def export_clip(source_path, selection_path, output_mp4):
    source, selection_path, output = map(Path, (source_path, selection_path, output_mp4))
    sidecar = output.with_suffix('.json')
    paths = (source, selection_path, output, sidecar)
    require(len({p.resolve() for p in paths}) == 4, 'Input/output paths overlap')
    require(source.is_file() and not source.is_symlink() and
            output.suffix.lower() == '.mp4' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists() and
            not sidecar.exists(), 'Unsafe input or output path')
    sel = validate_selection(read_selection(selection_path))
    require(digest_file(source) == sel['recording_sha256'], 'Recording SHA-256 mismatch')
    meta = probe(source)
    require(sel['end_seconds'] <= meta['duration_seconds'] + 0.01,
            'Clip exceeds video timeline')
    crop = sel['crop']
    if crop is not None:
        require(crop['x'] + crop['width'] <= meta['width'] and
                crop['y'] + crop['height'] <= meta['height'], 'Crop outside video')
    length = sel['end_seconds'] - sel['start_seconds']
    with tempfile.TemporaryDirectory(prefix='.plo-clip-', dir=output.parent) as tmp:
        temp = Path(tmp)
        srt = temp / 'human_explanation.srt'
        # Subtitle is explicitly human-authored, never a mathematical verdict.
        caption = 'Revisão humana (não verificada): ' + ' '.join(sel['explanation'].split())
        srt.write_text(f'1\n00:00:00,000 --> {_srt_time(length)}\n{caption}\n\n', encoding='utf-8')
        encoded = temp / 'clip.mp4'
        # FFmpeg can mark the last encoded packet DISCARD when output -t
        # equals the requested duration exactly (observed at 10 fps). A
        # 1 ms muxer rounding guard recovers that *existing* boundary frame
        # without padding or fabricating frames. It is not frame-exact proof.
        trim_end_guard_seconds = 0.001
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
               '-ss', str(sel['start_seconds']), '-i', str(source), '-i', str(srt),
               '-t', str(length + trim_end_guard_seconds), '-map', '0:v:0', '-map', '0:a:0?', '-map', '1:0',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-pix_fmt', 'yuv420p',
               '-fps_mode:v', 'passthrough',
               '-c:a', 'aac', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=por',
               '-movflags', '+faststart']
        # Accurate seeking may leave a nonzero first video PTS when the
        # selection starts between source frames. Rebase *observed* video PTS
        # to zero without manufacturing frames. Preserve VFR frame spacing.
        filters = []
        if crop is not None:
            filters.append(f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}")
        filters.append('setpts=PTS-STARTPTS')
        cmd += ['-vf', ','.join(filters)]
        cmd.append(str(encoded))
        _run(cmd, timeout=180)
        require(encoded.is_file() and encoded.stat().st_size > 0, 'Empty MP4')
        clip_meta = probe(encoded)
        video_timing = video_stream_timing(encoded)
        audio_timing = audio_stream_timing(encoded)
        require(abs(video_timing['start_seconds']) <= 0.025,
                'Exported video stream has nonzero initial PTS')
        require(abs(video_timing['duration_seconds'] - length) <= 0.25,
                'Exported video stream duration deviates from selection')
        require(abs(clip_meta['duration_seconds'] - length) <= 0.35,
                'Export duration deviates from requested interval')
        require(digest_file(source) == sel['recording_sha256'],
                'Recording changed during export')
        report = {'schema_version': 1, 'status': 'manual_clip_not_video_hand_verified',
                  'source_sha256': sel['recording_sha256'], 'selection': sel,
                  'output_sha256': digest_file(encoded), 'output_duration_seconds': clip_meta['duration_seconds'],
                  'subtitle_track': 'mov_text: human explanation',
                  'output_audio_stream_timing': audio_timing,
                  'output_audio_present': audio_timing is not None,
                  'output_audio_minus_video_start_seconds': (
                      round(audio_timing['start_seconds'] - video_timing['start_seconds'], 6)
                      if audio_timing is not None else None),
                  'output_audio_minus_video_end_seconds': (
                      round(audio_timing['start_seconds'] + audio_timing['duration_seconds']
                            - video_timing['start_seconds'] - video_timing['duration_seconds'], 6)
                      if audio_timing is not None else None),
                  'audio_video_content_sync_verified': False,
                  'output_trim_end_guard_seconds': trim_end_guard_seconds,
                  'output_video_stream_start_pts_seconds': video_timing['start_seconds'],
                  'output_video_stream_duration_seconds': video_timing['duration_seconds'],
                  'output_video_duration_shortfall_seconds': round(max(0.0, length - video_timing['duration_seconds']), 6),
                  'output_video_duration_overrun_seconds': round(max(0.0, video_timing['duration_seconds'] - length), 6),
                  'output_video_zero_based_stream_pts_verified': True,
                  'frame_exact_export_verified': False,
                  'source_pts_boundaries_verified': False,
                  'hand_reconstruction_verified': False, 'math_analysis_linked': False,
                  'strategic_error_established': False,
                  'automatic_clip_selection_authorized': False,
                  'warning': 'FFprobe checks container duration, not true hand boundaries. '
                             'Caption is a human statement, not a verified mathematical conclusion. '
                             'Video stream PTS is rebased, but a gap at the end can remain; '
                             'stream timing is not proof of frame identity. '
                             'A 1 ms output trim guard may admit boundary-adjacent frames; '
                             'source hand boundaries remain unverified. '
                             'Audio/video stream timing alone does not establish content synchronization.'}
        payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n'
        # Hard-link creation fails if output exists; no overwrite of user files.
        os.link(encoded, output)
        try:
            fd = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recorded_video')
    parser.add_argument('manual_selection_json')
    parser.add_argument('new_output_mp4')
    args = parser.parse_args(argv)
    result = export_clip(args.recorded_video, args.manual_selection_json, args.new_output_mp4)
    print(json.dumps({'status': result['status'], 'output_sha256': result['output_sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
