"""Create a bounded, SHA-256-bound, *approximate* offline preview frame.

This preview is only a visual aid for human confirmation of crop rectangles.
It does not authenticate cards, decisions, OCR, equity, or exact decision PTS.
FFmpeg fast seeking can land on a nearby decoded frame.
"""
import base64
import hashlib
import math
from pathlib import Path
import subprocess

from activity_clip_selection_editor import validate_unapproved_template
from video_validator import validate_recording

MAX_JPEG_BYTES = 2 * 1024 * 1024


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_region_preview(video_path, template, *, timestamp=None):
    """Extract one representative JPEG; never modify the recording or template."""
    validate_unapproved_template(template)
    info = validate_recording(video_path)
    expected = template['recording_sha256']
    if _file_sha256(video_path) != expected:
        raise ValueError('Recording SHA-256 mismatch before preview')
    if timestamp is None:
        timestamp = min(s['decision_timestamp'] for s in template['selections'])
    if (type(timestamp) not in (int, float) or not math.isfinite(timestamp)
            or not 0 <= timestamp < info['duration_seconds']):
        raise ValueError('Preview timestamp must be inside recording')
    # Input seeking is deliberately fast for 40–60 minute recordings. The
    # displayed frame is APPROXIMATE, not a certified decision timestamp.
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-ss', str(timestamp), '-i', str(video_path), '-an', '-sn', '-dn',
               '-frames:v', '1', '-vf', 'scale=w=min(960\\,iw):h=-2',
               '-q:v', '5', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
    try:
        completed = subprocess.run(command, check=True, capture_output=True, timeout=45)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg could not decode a preview frame') from exc
    data = completed.stdout
    if not 100 < len(data) <= MAX_JPEG_BYTES or not (data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')):
        raise ValueError('Invalid or oversized JPEG preview')
    if _file_sha256(video_path) != expected:
        raise ValueError('Recording changed while preview was generated')
    return {'recording_sha256': expected,
            'source_width': info['width'], 'source_height': info['height'],
            'requested_timestamp_seconds': float(timestamp),
            'jpeg_sha256': hashlib.sha256(data).hexdigest(),
            'jpeg_b64': base64.b64encode(data).decode('ascii'),
            'frame_timing': 'approximate_ffmpeg_fast_seek_not_decision_evidence'}
