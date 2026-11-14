"""Independent technical audit of offline table crops; no hand or strategy claims."""
import hashlib
import json
import math
import subprocess
from pathlib import Path


def _probe(path):
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
           '-show_entries', 'stream=width,height:frame=best_effort_timestamp_time',
           '-show_frames', '-of', 'json', str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=90)
    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    if len(streams) != 1:
        raise ValueError('exactly one video stream required')
    frames = data.get('frames', [])
    if not frames or len(frames) > 20000:
        raise ValueError('empty or excessive decoded frames')
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    if any(not math.isfinite(t) for t in pts) or any(b <= a for a, b in zip(pts, pts[1:])):
        raise ValueError('invalid frame timestamps')
    return streams[0], pts


def audit_table_crops(source, output_dir, *, duration_tolerance=0.25):
    """Audit manifest and crop files; crop PTS are relative, not source identity proof."""
    source, directory = Path(source), Path(output_dir)
    if source.is_symlink() or not source.is_file() or directory.is_symlink() or not directory.is_dir():
        raise ValueError('regular source and output directory required')
    if type(duration_tolerance) not in (int, float) or not math.isfinite(duration_tolerance) or not 0 <= duration_tolerance <= 2:
        raise ValueError('invalid tolerance')
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('missing manifest')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('status') != 'UNREVIEWED_TABLE_CROPS' or manifest.get('poker_analysis_verified') is not False:
        raise ValueError('manifest claims unsupported verification')
    tables = manifest.get('tables')
    if not isinstance(tables, list) or not 1 <= len(tables) <= 4:
        raise ValueError('invalid table count')
    source_stream, source_pts = _probe(source)
    if manifest.get('source_dimensions') != [source_stream['width'], source_stream['height']]:
        raise ValueError('source dimensions changed')
    seen = set()
    audited = []
    for table in tables:
        if not isinstance(table, dict) or table.get('verified_by_human') is not False or table.get('hand_reconstructed') is not False:
            raise ValueError('unsupported table verification')
        table_id = table.get('table_id')
        if type(table_id) is not int or table_id not in range(1, 5) or table_id in seen:
            raise ValueError('invalid table id')
        seen.add(table_id)
        if table.get('file') != f'table_{table_id}.mkv':
            raise ValueError('unexpected crop filename')
        region = table.get('region')
        if not isinstance(region, dict) or region.get('table_id') != table_id:
            raise ValueError('region identity mismatch')
        x, y, w, h = (region.get(k) for k in ('x', 'y', 'width', 'height'))
        if any(type(v) is not int for v in (x, y, w, h)) or x < 0 or y < 0 or w < 2 or h < 2 or x+w > source_stream['width'] or y+h > source_stream['height']:
            raise ValueError('invalid crop geometry')
        start, duration = table.get('source_start_seconds'), table.get('requested_duration_seconds')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, duration)) or start < 0 or not 0 < duration <= 300:
            raise ValueError('invalid source interval')
        if not any(start - duration_tolerance <= p <= start + duration + duration_tolerance for p in source_pts):
            raise ValueError('no source frames in requested interval')
        path = directory / table['file']
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing regular crop')
        stream, pts = _probe(path)
        if (stream['width'], stream['height']) != (w, h):
            raise ValueError('crop dimensions mismatch')
        if pts[-1] - pts[0] > duration + duration_tolerance or pts[-1] - pts[0] < max(0, duration - duration_tolerance - 0.2):
            raise ValueError('crop timeline mismatch')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        audited.append({'table_id': table_id, 'sha256': digest, 'decoded_frames': len(pts),
                        'first_crop_pts': pts[0], 'last_crop_pts': pts[-1],
                        'status': 'TECHNICAL_CROP_ONLY'})
    return {'status': 'TECHNICAL_CROPS_AUDITED_ONLY', 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'tables': audited, 'visual_identity_verified': False, 'hands_verified': False,
            'equity_ev_verified': False}
