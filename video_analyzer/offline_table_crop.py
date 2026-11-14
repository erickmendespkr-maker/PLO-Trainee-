"""Offline bounded table-region crop exporter; never infers poker events."""
import json
import math
import subprocess
from pathlib import Path

def validate_regions(regions, width, height):
    if type(width) is not int or type(height) is not int or width < 2 or height < 2:
        raise ValueError('invalid source dimensions')
    if not isinstance(regions, list) or not 1 <= len(regions) <= 4:
        raise ValueError('expected 1-4 table regions')
    ids = set()
    for region in regions:
        if not isinstance(region, dict) or set(region) != {'table_id', 'x', 'y', 'width', 'height'}:
            raise ValueError('invalid region fields')
        table_id = region['table_id']
        if type(table_id) is not int or not 1 <= table_id <= 4 or table_id in ids:
            raise ValueError('invalid or duplicate table id')
        ids.add(table_id)
        x, y, w, h = (region[k] for k in ('x', 'y', 'width', 'height'))
        if any(type(v) is not int for v in (x, y, w, h)):
            raise ValueError('region coordinates must be integers')
        if x < 0 or y < 0 or w < 2 or h < 2 or x+w > width or y+h > height:
            raise ValueError('region outside source frame')
    return sorted(regions, key=lambda r: r['table_id'])

def probe_dimensions(source):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                             '-show_entries', 'stream=width,height', '-of', 'json', str(source)],
                            capture_output=True, text=True, check=True, timeout=30)
    streams = json.loads(result.stdout).get('streams', [])
    if len(streams) != 1:
        raise ValueError('expected exactly one selected video stream')
    return streams[0]['width'], streams[0]['height']

def export_table_crops(source, output_dir, regions, *, start_seconds, duration_seconds):
    """Export lossless FFV1 Matroska crops for offline visual/OCR inspection."""
    source = Path(source)
    output_dir = Path(output_dir)
    if source.is_symlink() or not source.is_file():
        raise ValueError('regular source file required')
    if output_dir.is_symlink():
        raise ValueError('output directory must not be symlink')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start_seconds, duration_seconds)):
        raise ValueError('invalid timeline')
    if start_seconds < 0 or not 0 < duration_seconds <= 300:
        raise ValueError('invalid crop interval')
    width, height = probe_dimensions(source)
    validated = validate_regions(regions, width, height)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError('output directory must be empty')
    outputs = []
    for region in validated:
        destination = output_dir / f"table_{region['table_id']}.mkv"
        crop = f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                   '-ss', str(start_seconds), '-i', str(source), '-t', str(duration_seconds),
                   '-map', '0:v:0', '-an', '-vf', crop, '-c:v', 'ffv1', str(destination)]
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        outputs.append({'table_id': region['table_id'], 'file': destination.name,
                        'region': region, 'source_start_seconds': start_seconds,
                        'requested_duration_seconds': duration_seconds,
                        'verified_by_human': False, 'hand_reconstructed': False})
    manifest = {'status': 'UNREVIEWED_TABLE_CROPS', 'source_dimensions': [width, height],
                'tables': outputs, 'poker_analysis_verified': False}
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
