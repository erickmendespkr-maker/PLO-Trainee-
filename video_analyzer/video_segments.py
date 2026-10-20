"""Offline video frame sampling and clip extraction with FFmpeg."""
import json
import subprocess
from pathlib import Path


def _run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def probe_video(path):
    result = _run(['ffprobe', '-v', 'error', '-show_entries',
                   'format=duration:stream=codec_type,width,height',
                   '-of', 'json', str(path)])
    info = json.loads(result.stdout)
    video = next((s for s in info.get('streams', [])
                  if s.get('codec_type') == 'video'), None)
    if video is None:
        raise ValueError('Video stream not found')
    return {'duration': float(info['format']['duration']),
            'width': video['width'], 'height': video['height']}


def sample_frames(source, output_dir, interval_seconds=2):
    if interval_seconds <= 0:
        raise ValueError('interval_seconds must be positive')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pattern = out / 'frame_%06d.jpg'
    _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
          '-y', '-i', str(source), '-vf', f'fps=1/{interval_seconds}',
          '-q:v', '3', str(pattern)])
    return sorted(out.glob('frame_*.jpg'))


def extract_clip(source, output, start_seconds, end_seconds):
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError('Invalid clip timestamps')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
          '-y', '-ss', str(start_seconds), '-i', str(source),
          '-t', str(end_seconds - start_seconds),
          '-c:v', 'libx264', '-c:a', 'aac',
          '-movflags', '+faststart', str(output)])
    return output
