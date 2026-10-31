"""Offline, unverified table-layout proposals from a *recorded* video.

Uses FFmpeg/FFprobe and the Python standard library. Candidate seams are
heuristics, not table recognition. No poker client, live feed or OCR access.

Propose: python offline_table_region_proposals.py propose VIDEO OUT_DIR
Review:  open OUT_DIR/preview.png and OUT_DIR/proposals.json
Confirm: python offline_table_region_proposals.py confirm VIDEO OUT_DIR/proposals.json \
         OUT_DIR/manual_layout.json --confirm-reviewed

Confirmation is an explicit human action. Never call confirm automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile

W, H = 160, 90
MAX_BYTES = 15_000_000_000
MAX_DURATION = 7200
STATUS = 'offline_table_region_proposals_unverified'
MANUAL_STATUS = 'manual_offline_table_regions_unverified'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def safe_file(path, *, max_size=MAX_BYTES):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing or symlink input')
    require(0 < path.stat().st_size <= max_size, 'empty or oversized input')
    return path


def sha256(path):
    h = hashlib.sha256()
    with safe_file(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def no_constant(value):
        raise ValueError('non-finite JSON value')
    return json.loads(safe_file(path, max_size=2_000_000).read_text(encoding='utf-8'),
                      object_pairs_hook=unique_pairs, parse_constant=no_constant)


def run(args, *, timeout=60, cwd=None):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout, cwd=cwd)


def probe(video):
    result = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                  '-show_entries', 'stream=width,height:format=duration',
                  '-of', 'json', str(video)], timeout=30)
    data = json.loads(result.stdout)
    require(len(data.get('streams', [])) == 1, 'missing video stream')
    stream = data['streams'][0]
    width, height = stream['width'], stream['height']
    duration = float(data['format']['duration'])
    require(type(width) is int and type(height) is int and
            64 <= width <= 16384 and 64 <= height <= 16384 and
            math.isfinite(duration) and 0.5 <= duration <= MAX_DURATION,
            'invalid video geometry or duration')
    return width, height, duration


def sample(video, timestamp):
    result = run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{timestamp:.6f}',
                  '-i', str(video), '-frames:v', '1', '-vf',
                  f'scale={W}:{H},format=gray', '-f', 'rawvideo', '-'], timeout=60)
    require(len(result.stdout) == W * H, 'missing/incomplete sampled frame')
    return result.stdout


def seam(frame, vertical):
    """Mean absolute neighbor contrast along every candidate dividing line."""
    if vertical:
        return [sum(abs(frame[y * W + x] - frame[y * W + x - 1])
                    for y in range(H)) / H for x in range(1, W)]
    return [sum(abs(frame[y * W + x] - frame[(y - 1) * W + x])
                for x in range(W)) / W for y in range(1, H)]


def best_axis(frames, vertical):
    n = W if vertical else H
    measurements = [seam(frame, vertical) for frame in frames]
    averaged = [statistics.mean(m[i] for m in measurements) for i in range(n - 1)]
    # Only inspect plausible central table separations; ignore screen borders.
    indices = range(math.ceil(n * .30), math.floor(n * .70) + 1)
    best = max(indices, key=lambda i: (averaged[i - 1], -abs(i - n / 2)))
    strength = averaged[best - 1]
    baseline = statistics.median(averaged)
    ratio = strength / max(1.0, baseline)
    supported = strength >= 12.0 and ratio >= 3.0
    return {'position_sample_px': best, 'contrast': round(strength, 4),
            'contrast_to_median_ratio': round(ratio, 4),
            'supported_by_heuristic': supported,
            'note': 'Uncalibrated contrast evidence, not probability of a table.'}


def even(value):
    return max(2, int(value) // 2 * 2)


def propose_regions(width, height, xaxis, yaxis):
    usable_w, usable_h = even(width), even(height)
    xcut = even(round(width * xaxis['position_sample_px'] / W)) if xaxis['supported_by_heuristic'] else None
    ycut = even(round(height * yaxis['position_sample_px'] / H)) if yaxis['supported_by_heuristic'] else None
    if xcut is not None and not 2 <= xcut <= usable_w - 2:
        xcut = None
    if ycut is not None and not 2 <= ycut <= usable_h - 2:
        ycut = None
    xs = [(0, usable_w)] if xcut is None else [(0, xcut), (xcut, usable_w - xcut)]
    ys = [(0, usable_h)] if ycut is None else [(0, ycut), (ycut, usable_h - ycut)]
    return [{'table_id': f'T{len(xs) * j + i + 1}', 'x': x, 'y': y,
             'width': w, 'height': h}
            for j, (y, h) in enumerate(ys) for i, (x, w) in enumerate(xs)]


def make_preview(video, timestamp, regions, target):
    filters = []
    for region in regions:
        r = region
        filters.append(f"drawbox=x={r['x']}:y={r['y']}:w={r['width']}:h={r['height']}:"
                       'color=yellow@0.9:t=3')
    run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{timestamp:.6f}',
         '-i', str(video), '-frames:v', '1', '-vf', ','.join(filters),
         '-y', str(target)], timeout=60)
    safe_file(target, max_size=30_000_000)


def propose(video, output_dir):
    video, output_dir = Path(video), Path(output_dir)
    require(video.suffix.lower() in ('.mp4', '.webm', '.mov'), 'unsupported extension')
    safe_file(video)
    require(output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe output dir')
    require(output_dir.resolve() != video.parent.resolve(), 'use a separate output directory')
    require(not (output_dir / 'proposals.json').exists() and
            not (output_dir / 'proposals.json').is_symlink() and
            not (output_dir / 'preview.png').exists() and
            not (output_dir / 'preview.png').is_symlink(), 'output already exists')
    width, height, duration = probe(video)
    original_hash = sha256(video)
    timestamps = [round(duration * factor, 6) for factor in (.15, .50, .85)]
    frames = [sample(video, t) for t in timestamps]
    xaxis, yaxis = best_axis(frames, True), best_axis(frames, False)
    regions = propose_regions(width, height, xaxis, yaxis)
    payload = {'schema_version': 1, 'status': STATUS,
               'source_video_sha256': original_hash,
               'source_width': width, 'source_height': height,
               'source_duration_seconds': duration,
               'sample_timestamps_seconds': timestamps,
               'method': 'central_neighbor_contrast_ffmpeg_gray_160x90_v1',
               'vertical_seam_evidence': xaxis, 'horizontal_seam_evidence': yaxis,
               'regions': regions, 'human_confirmation': False,
               'automatic_ocr_math_authorization': False,
               'warning': 'Unverified geometric proposal only. Review preview and video; no automatic crop authorization or strategy verdict.'}
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_layout_', dir=output_dir) as folder:
            preview = Path(folder) / 'preview.png'
            make_preview(video, timestamps[1], regions, preview)
            require(sha256(video) == original_hash, 'video changed during sampling')
            payload['preview_sha256'] = sha256(preview)
            draft = Path(folder) / 'proposals.json'
            draft.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
            require(sha256(video) == original_hash, 'video changed before publishing')
            for src, dest in ((preview, output_dir / 'preview.png'),
                              (draft, output_dir / 'proposals.json')):
                require(not dest.exists() and not dest.is_symlink(), 'output collision')
                os.link(src, dest)
                created.append(dest)
    except BaseException:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise
    return payload


def confirm(video, proposal_json, manual_json, *, confirmed=False):
    """Human-triggered conversion to the existing manual crop layout schema."""
    require(confirmed is True, 'human must explicitly confirm reviewed geometry')
    video, proposal_json, manual_json = map(Path, (video, proposal_json, manual_json))
    safe_file(video)
    require(not manual_json.exists() and not manual_json.is_symlink(), 'output collision')
    p = read_json(proposal_json)
    width, height, duration = probe(video)
    require(type(p) is dict and p.get('schema_version') == 1 and
            p.get('status') == STATUS and p.get('human_confirmation') is False and
            p.get('automatic_ocr_math_authorization') is False and
            p.get('source_video_sha256') == sha256(video) and
            p.get('source_width') == width and p.get('source_height') == height and
            p.get('source_duration_seconds') == duration and
            type(p.get('regions')) is list and 1 <= len(p['regions']) <= 4,
            'invalid proposal or source video')
    require(p.get('preview_sha256') == sha256(proposal_json.parent / 'preview.png'),
            'preview integrity mismatch')
    # A changed JSON region must never be silently approved against an older preview.
    timestamps = [round(duration * factor, 6) for factor in (.15, .50, .85)]
    require(p.get('sample_timestamps_seconds') == timestamps and
            p.get('method') == 'central_neighbor_contrast_ffmpeg_gray_160x90_v1',
            'proposal sampling provenance mismatch')
    frames = [sample(video, t) for t in timestamps]
    xaxis, yaxis = best_axis(frames, True), best_axis(frames, False)
    require(p.get('vertical_seam_evidence') == xaxis and
            p.get('horizontal_seam_evidence') == yaxis and
            p['regions'] == propose_regions(width, height, xaxis, yaxis),
            'proposal geometry changed since evidence was sampled')
    seen = set()
    for r in p['regions']:
        require(type(r) is dict and set(r) == {'table_id','x','y','width','height'} and
                type(r['table_id']) is str and r['table_id'].startswith('T') and
                r['table_id'][1:].isdigit() and r['table_id'] not in seen and
                all(type(r[k]) is int for k in ('x','y','width','height')) and
                r['x'] >= 0 and r['y'] >= 0 and r['width'] >= 2 and r['height'] >= 2 and
                r['width'] % 2 == 0 and r['height'] % 2 == 0 and
                r['x'] + r['width'] <= width and r['y'] + r['height'] <= height,
                'invalid region')
        seen.add(r['table_id'])
    layout = {'schema_version': 1, 'status': MANUAL_STATUS,
              'source_video_sha256': p['source_video_sha256'], 'regions': p['regions']}
    manual_json.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='plo_manual_', dir=manual_json.parent) as folder:
        tmp = Path(folder) / 'layout.json'
        tmp.write_text(json.dumps(layout, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        require(sha256(video) == p['source_video_sha256'] and
                sha256(proposal_json.parent / 'preview.png') == p['preview_sha256'],
                'source changed during confirmation')
        require(not manual_json.exists() and not manual_json.is_symlink(), 'output collision')
        os.link(tmp, manual_json)
    return layout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('propose')
    a.add_argument('video')
    a.add_argument('output_dir')
    b = sub.add_parser('confirm')
    b.add_argument('video')
    b.add_argument('proposals_json')
    b.add_argument('manual_layout_json')
    b.add_argument('--confirm-reviewed', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'propose':
        result = propose(args.video, args.output_dir)
        print(json.dumps({'status': result['status'], 'region_count': len(result['regions'])}))
    else:
        result = confirm(args.video, args.proposals_json, args.manual_layout_json,
                         confirmed=args.confirm_reviewed)
        print(json.dumps({'status': result['status'], 'region_count': len(result['regions'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
