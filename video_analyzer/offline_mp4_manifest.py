"""Offline MP4 evidence manifest; never claims hand recognition or strategic correctness."""
import hashlib
import json
import math
import subprocess
from pathlib import Path


def manifest(video_path, start_seconds, end_seconds, source_sha256, table_id):
    path = Path(video_path)
    if not path.is_file() or path.suffix.lower() != '.mp4':
        raise ValueError('MP4 file required')
    if type(table_id) is not int or not 1 <= table_id <= 4:
        raise ValueError('invalid table id')
    if type(source_sha256) is not str or len(source_sha256) != 64 or any(c not in '0123456789abcdef' for c in source_sha256):
        raise ValueError('invalid source hash')
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in (start_seconds, end_seconds)) or not 0 <= start_seconds < end_seconds:
        raise ValueError('invalid timestamps')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height:format=duration', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    data = json.loads(probe.stdout)
    if not data.get('streams') or data['streams'][0].get('codec_name') is None:
        raise ValueError('no video stream')
    duration = float(data['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid duration')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'schema_version': 1, 'clip_sha256': digest.hexdigest(), 'source_video_sha256': source_sha256, 'table_id': table_id, 'source_start_seconds': start_seconds, 'source_end_seconds': end_seconds, 'clip_duration_seconds': duration, 'video_codec': data['streams'][0]['codec_name'], 'width': data['streams'][0]['width'], 'height': data['streams'][0]['height'], 'analysis_status': 'INSUFFICIENT_DATA', 'hand_reconstruction_verified': False, 'strategic_error_established': False, 'gto_solution': False}
