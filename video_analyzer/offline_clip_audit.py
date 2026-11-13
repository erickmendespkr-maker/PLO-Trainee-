"""Audit an offline MP4 export and its JSON sidecar; no strategic verdict."""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path


def audit_export(mp4_path, *, expected_source_sha256=None, expected_hand_id=None, expected_table_id=None, expected_interval=None, expected_review_status=None, tolerance_seconds=0.25):
    path = Path(mp4_path)
    sidecar = path.with_name(path.name + '.json')
    if path.suffix.lower() != '.mp4' or not path.is_file() or path.is_symlink():
        raise ValueError('regular MP4 required')
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError('regular JSON sidecar required')
    if type(tolerance_seconds) not in (int, float) or not math.isfinite(tolerance_seconds) or not 0 <= tolerance_seconds <= 1:
        raise ValueError('invalid duration tolerance')
    metadata = json.loads(sidecar.read_text(encoding='utf-8'))
    if not isinstance(metadata, dict) or metadata.get('schema_version') != 1:
        raise ValueError('unsupported sidecar')
    for key in ('source_sha256', 'clip_sha256'):
        value = metadata.get(key)
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('invalid hash field: ' + key)
    if expected_source_sha256 is not None and metadata['source_sha256'] != expected_source_sha256:
        raise ValueError('source hash mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != metadata['clip_sha256']:
        raise ValueError('clip hash mismatch')
    hand_id = metadata.get('hand_id')
    if type(hand_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', hand_id) is None:
        raise ValueError('invalid hand id')
    if expected_hand_id is not None and (type(expected_hand_id) is not str or hand_id != expected_hand_id):
        raise ValueError('hand identity mismatch')
    if type(metadata.get('table_id')) is not int or not 1 <= metadata['table_id'] <= 4:
        raise ValueError('invalid table id')
    if expected_table_id is not None and (type(expected_table_id) is not int or metadata['table_id'] != expected_table_id):
        raise ValueError('table identity mismatch')
    start, end, recorded = (metadata.get(k) for k in ('start_seconds', 'end_seconds', 'actual_clip_duration_seconds'))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end, recorded)) or not 0 <= start < end or recorded <= 0:
        raise ValueError('invalid timestamps')
    if expected_interval is not None:
        if (not isinstance(expected_interval, (tuple, list)) or len(expected_interval) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in expected_interval)
                or not 0 <= expected_interval[0] < expected_interval[1]
                or abs(start - expected_interval[0]) > 1e-6 or abs(end - expected_interval[1]) > 1e-6):
            raise ValueError('source interval mismatch')
    if abs(recorded - (end - start)) > tolerance_seconds:
        raise ValueError('sidecar interval mismatch')
    if metadata.get('strategic_verdict_allowed') is not False or metadata.get('review_status') not in ('confirmed', 'insufficient_data'):
        raise ValueError('invalid review gate')
    if expected_review_status is not None and (expected_review_status not in ('confirmed', 'insufficient_data') or metadata['review_status'] != expected_review_status):
        raise ValueError('review status mismatch')
    expected_annotation = ('INSUFFICIENT_DATA' if metadata['review_status'] == 'insufficient_data'
                           else 'CONDITIONAL MODEL ONLY')
    if metadata.get('annotation') != expected_annotation:
        raise ValueError('annotation does not match review status')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name:format=duration', '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(probe.stdout)
    if not data.get('streams') or not data['streams'][0].get('codec_name'):
        raise ValueError('no video stream')
    measured = float(data['format']['duration'])
    if not math.isfinite(measured) or abs(measured - recorded) > tolerance_seconds:
        raise ValueError('ffprobe duration mismatch')
    return {'clip_sha256': metadata['clip_sha256'], 'source_sha256': metadata['source_sha256'], 'table_id': metadata['table_id'], 'source_start_seconds': start, 'source_end_seconds': end, 'measured_duration_seconds': measured, 'integrity_verified': True, 'hand_reconstruction_verified': False, 'strategic_error_established': False, 'gto_solution': False}
