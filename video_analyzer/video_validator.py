"""Guardrails for offline recorded-video processing."""
from pathlib import Path
from video_segments import probe_video

ALLOWED_EXTENSIONS = {'.mp4', '.webm'}
MAX_DURATION_SECONDS = 3600
MAX_SIZE_BYTES = 4 * 1024 ** 3

def validate_recording(path, *, max_duration=MAX_DURATION_SECONDS, max_bytes=MAX_SIZE_BYTES):
    path = Path(path)
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError('Only MP4 and WebM recordings are accepted')
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if not 0 < size <= max_bytes:
        raise ValueError('Invalid recording size')
    info = probe_video(path)
    if not 0 < info['duration'] <= max_duration:
        raise ValueError('Recording exceeds maximum duration')
    if not 0 < info['width'] <= 8192 or not 0 < info['height'] <= 8192:
        raise ValueError('Invalid video dimensions')
    return {'size_bytes': size, 'duration_seconds': info['duration'],
            'width': info['width'], 'height': info['height'],
            'max_duration_seconds': max_duration, 'max_size_bytes': max_bytes}
