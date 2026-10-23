"""Bounded, offline FFmpeg contact frames for manual *temporal* crop review.

These frames are approximate visual aids, not evidence of a poker action or
proof that crops remain stable between sampled timestamps. Never auto-approve.
"""
import base64
import hashlib
import math
import subprocess

from activity_clip_region_preview import MAX_JPEG_BYTES, _file_sha256
from activity_clip_selection_editor import validate_unapproved_template
from video_validator import validate_recording

MAX_FRAMES = 5
MAX_TOTAL_JPEG_BYTES = 6 * 1024 * 1024
TIMING = 'approximate_ffmpeg_fast_seek_not_decision_evidence'


def _timestamps(duration, timestamps):
    if timestamps is None:
        timestamps = [duration * fraction for fraction in (.1, .5, .9)]
    if (not isinstance(timestamps, (tuple, list))
            or not 2 <= len(timestamps) <= MAX_FRAMES):
        raise ValueError('Require 2 to 5 preview timestamps')
    previous = -1.0
    result = []
    for value in timestamps:
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not previous < value < duration):
            raise ValueError('Preview timestamps must increase inside recording')
        previous = float(value)
        result.append(float(value))
    return result


def build_region_preview_timeline(video_path, template, *, timestamps=None):
    """Sample 2–5 JPEGs, with a single video identity check before and after.

    FFmpeg is run without shell interpolation, network input, or external data.
    Each frame's requested seek time is approximate; actual PTS is not asserted.
    """
    validate_unapproved_template(template)
    info = validate_recording(video_path)
    times = _timestamps(info['duration_seconds'], timestamps)
    expected = template['recording_sha256']
    if _file_sha256(video_path) != expected:
        raise ValueError('Recording SHA-256 mismatch before preview timeline')
    frames = []
    total = 0
    for timestamp in times:
        command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-ss', str(timestamp), '-i', str(video_path), '-an', '-sn', '-dn',
                   '-frames:v', '1', '-vf', 'scale=w=min(960\\,iw):h=-2',
                   '-q:v', '5', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
        try:
            result = subprocess.run(command, check=True, capture_output=True, timeout=45)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise ValueError('FFmpeg could not decode timeline frame') from exc
        data = result.stdout
        if (not 100 < len(data) <= MAX_JPEG_BYTES
                or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9')):
            raise ValueError('Invalid or oversized JPEG timeline frame')
        total += len(data)
        if total > MAX_TOTAL_JPEG_BYTES:
            raise ValueError('Timeline JPEGs exceed combined byte limit')
        frames.append({'recording_sha256': expected,
                       'source_width': info['width'], 'source_height': info['height'],
                       'requested_timestamp_seconds': timestamp,
                       'jpeg_sha256': hashlib.sha256(data).hexdigest(),
                       'jpeg_b64': base64.b64encode(data).decode('ascii'),
                       'frame_timing': TIMING})
    if _file_sha256(video_path) != expected:
        raise ValueError('Recording changed during preview timeline generation')
    return {'schema_version': 1, 'recording_sha256': expected, 'frames': frames}
