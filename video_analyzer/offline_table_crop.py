"""Offline bounded table-region crop exporter; never infers poker events."""
import json
import math
import subprocess
from pathlib import Path

try:
    from .offline_table_crop_geometry_integration import validated_table_regions
except ImportError:  # direct script/test execution from video_analyzer/
    from offline_table_crop_geometry_integration import validated_table_regions

def validate_regions(regions, width, height):
    """Reject overlapping, odd-pixel and out-of-frame table ROIs before FFmpeg."""
    return [
        {key: region[key] for key in ('table_id', 'x', 'y', 'width', 'height')}
        for region in validated_table_regions(width, height, regions)
    ]

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
    created = []
    try:
        for region in validated:
            destination = output_dir / f"table_{region['table_id']}.mkv"
            crop = f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                       '-ss', str(start_seconds), '-i', str(source), '-t', str(duration_seconds),
                       '-map', '0:v:0', '-an', '-vf', crop, '-c:v', 'ffv1', str(destination)]
            subprocess.run(command, check=True, capture_output=True, timeout=180)
            created.append(destination)
            outputs.append({'table_id': region['table_id'], 'file': destination.name,
                            'region': region, 'source_start_seconds': start_seconds,
                            'requested_duration_seconds': duration_seconds,
                            'verified_by_human': False, 'hand_reconstructed': False})
    except Exception:
        for artifact in created:
            artifact.unlink(missing_ok=True)
        for region in validated:
            (output_dir / f"table_{region['table_id']}.mkv").unlink(missing_ok=True)
        raise
    manifest = {'status': 'UNREVIEWED_TABLE_CROPS', 'source_dimensions': [width, height],
                'tables': outputs, 'poker_analysis_verified': False}
    try:
        (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    except Exception:
        for artifact in created:
            artifact.unlink(missing_ok=True)
        raise
    return manifest
