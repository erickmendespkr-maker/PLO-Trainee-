"""Plan safe offline MP4 clips from timestamped recorded hands; no FFmpeg execution."""
import math
from pathlib import Path


def _num(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{label} must be finite and nonnegative')
    return float(value)


def plan_clip(hand, *, source, destination, duration_seconds, pad_before=3, pad_after=3):
    if not isinstance(hand, dict):
        raise ValueError('hand must be object')
    duration = _num(duration_seconds, 'duration_seconds')
    before = _num(pad_before, 'pad_before')
    after = _num(pad_after, 'pad_after')
    start = _num(hand.get('start_seconds'), 'start_seconds')
    end = _num(hand.get('end_seconds'), 'end_seconds')
    if not (0 <= start < end <= duration):
        raise ValueError('invalid hand interval')
    if not isinstance(hand.get('hand_id'), str) or not hand['hand_id'].strip():
        raise ValueError('hand_id required')
    if not isinstance(hand.get('table_id'), int) or isinstance(hand['table_id'], bool) or not 1 <= hand['table_id'] <= 4:
        raise ValueError('table_id must be 1..4')
    src, dst = Path(source), Path(destination)
    if src.suffix.lower() not in ('.mp4', '.webm', '.mkv') or dst.suffix.lower() != '.mp4':
        raise ValueError('unsupported source or destination format')
    if src.resolve() == dst.resolve():
        raise ValueError('source and destination must differ')
    a, b = max(0.0, start-before), min(duration, end+after)
    args = ['ffmpeg', '-hide_banner', '-nostdin', '-n', '-i', str(src),
            '-ss', f'{a:.3f}', '-t', f'{b-a:.3f}', '-map', '0:v:0', '-map', '0:a?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-c:a', 'aac',
            '-movflags', '+faststart', str(dst)]
    return {'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
            'start_seconds': a, 'end_seconds': b, 'ffmpeg_argv': args,
            'status': 'PLANNED_NOT_EXPORTED', 'financial_result_verified': False,
            'analysis_verified': False}
