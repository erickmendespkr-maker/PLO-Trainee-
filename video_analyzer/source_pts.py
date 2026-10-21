"""Read FFmpeg showinfo frame timestamps without assuming constant FPS."""
import math


def parse_source_pts(log):
    if not isinstance(log, str):
        raise TypeError('Expected FFmpeg diagnostic text')
    rows = []
    for line in log.splitlines():
        if '[Parsed_showinfo_' not in line or ' n:' not in line or ' pts_time:' not in line:
            continue
        try:
            number = int(line.split(' n:', 1)[1].split()[0])
            value = float(line.split(' pts_time:', 1)[1].split()[0])
        except (ValueError, IndexError) as exc:
            raise ValueError('Invalid decoded frame PTS') from exc
        if not math.isfinite(value):
            raise ValueError('Invalid decoded frame PTS')
        if number != len(rows):
            raise ValueError('Missing, duplicated or out-of-order decoded frame PTS')
        if rows and value <= rows[-1][1]:
            raise ValueError('Decoded frame PTS must be strictly increasing')
        rows.append((number, value))
    if not rows:
        raise ValueError('FFmpeg showinfo returned no decoded frame timestamps')
    return rows
