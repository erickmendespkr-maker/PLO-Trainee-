"""Offline FFmpeg/Tesseract extraction of *unverified* OCR proposals.

Usage: python offline_ffmpeg_tesseract_proposals.py VIDEO PLAN.json ROI_SPEC.json NEW_PROPOSALS.json

ROI_SPEC is a manually supplied, video-frame-normalized sampling specification.
This does NOT detect hands, tables, cards, or actions automatically. Every OCR
result is unverified and must pass independent human frame review before equity.
No network access or real-time poker integration.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile

import offline_ocr_review_bridge as bridge
import offline_reviewed_hand_math_queue as queue

MAX_SAMPLES = 6000
MAX_VIDEO_BYTES = 8 * 1024**3
MAX_DIMENSION = 8192
MAX_DURATION = 3600


def run(command, timeout):
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError('offline media/OCR command failed: ' + command[0]) from exc


def probe(video):
    result = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                  '-show_entries', 'stream=width,height:format=duration',
                  '-of', 'json', str(video)], 30)
    info = json.loads(result.stdout)
    streams = info.get('streams', [])
    queue.require(len(streams) == 1, 'video stream unavailable')
    width, height = streams[0].get('width'), streams[0].get('height')
    duration = float(info.get('format', {}).get('duration', 0))
    queue.require(type(width) is int and type(height) is int and
                  64 <= width <= MAX_DIMENSION and 64 <= height <= MAX_DIMENSION and
                  math.isfinite(duration) and .1 <= duration <= MAX_DURATION,
                  'invalid video geometry or duration')
    return width, height, duration


def validate_spec(spec, clips, duration):
    queue.require(type(spec) is dict and set(spec) == {'schema_version', 'status', 'samples'} and
                  spec['schema_version'] == 1 and
                  spec['status'] == 'human_declared_offline_roi_samples' and
                  type(spec['samples']) is list and 1 <= len(spec['samples']) <= MAX_SAMPLES,
                  'invalid manual ROI sample specification')
    allowed = {'hand_id', 'table_id', 'field', 'slot', 'pts_seconds', 'roi'}
    seen = set()
    for row in spec['samples']:
        queue.require(type(row) is dict and set(row) == allowed and
                      type(row['hand_id']) is str and row['hand_id'] in clips,
                      'invalid sample fields or hand')
        clip = clips[row['hand_id']]
        queue.require(row['table_id'] == clip['table_id'], 'cross-table sample')
        field, slot = row['field'], row['slot']
        queue.require(type(field) is str and field in bridge.FIELDS, 'invalid sample field')
        if field in ('hero_card', 'board_card'):
            queue.require(type(slot) is int and 0 <= slot < (6 if field == 'hero_card' else 5),
                          'invalid card slot')
        else:
            queue.require(slot is None, 'non-card sample slot')
        pts = row['pts_seconds']
        queue.require(bridge.number(pts, clip['start_seconds'], clip['end_seconds']) and
                      pts < duration, 'sample timestamp outside video/hand')
        roi = row['roi']
        queue.require(type(roi) is dict and set(roi) == {'x', 'y', 'w', 'h'} and
                      all(bridge.number(roi[k], 0, 1) for k in roi) and
                      roi['w'] > 0 and roi['h'] > 0 and
                      roi['x'] + roi['w'] <= 1 + 1e-9 and
                      roi['y'] + roi['h'] <= 1 + 1e-9,
                      'invalid normalized ROI')
        key = (row['hand_id'], field, slot, pts, *(roi[k] for k in ('x', 'y', 'w', 'h')))
        queue.require(key not in seen, 'duplicate OCR sample')
        seen.add(key)
    return spec['samples']


def pixel_crop(roi, width, height):
    x = round(roi['x'] * width)
    y = round(roi['y'] * height)
    w = round(roi['w'] * width)
    h = round(roi['h'] * height)
    queue.require(w >= 12 and h >= 12 and x >= 0 and y >= 0 and
                  x + w <= width and y + h <= height,
                  'ROI too small or outside decoded frame')
    return x, y, w, h


def ocr_image(image):
    result = run(['tesseract', str(image), 'stdout', '--psm', '7', 'tsv'], 30)
    rows = list(csv.DictReader(io.StringIO(result.stdout), delimiter='\t'))
    words = []
    for row in rows:
        word = (row.get('text') or '').strip()
        if not word:
            continue
        try:
            confidence = float(row.get('conf', '-1'))
        except ValueError:
            continue
        if math.isfinite(confidence) and 0 <= confidence <= 100:
            words.append((word, confidence))
    if not words:
        return None
    raw = ' '.join(word for word, _ in words)
    if not (1 <= len(raw) <= bridge.MAX_TEXT and all(32 <= ord(c) < 127 for c in raw)):
        return None
    return raw, min(conf for _, conf in words) / 100


def build(video, plan, spec):
    video = Path(video)
    queue.require(video.is_file() and not video.is_symlink() and
                  0 < video.stat().st_size <= MAX_VIDEO_BYTES and
                  video.suffix.lower() in ('.mp4', '.webm'),
                  'invalid local video')
    clips = queue.validate_plan(plan)
    video_sha = queue.digest(video)
    queue.require(video_sha == plan['source_video_sha256'], 'video SHA-256 differs from plan')
    width, height, duration = probe(video)
    samples = validate_spec(spec, clips, duration)
    observations = []
    skipped = 0
    with tempfile.TemporaryDirectory(prefix='plo_offline_ocr_') as directory:
        image = Path(directory) / 'sample.png'
        for sample in samples:
            x, y, w, h = pixel_crop(sample['roi'], width, height)
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                 '-ss', str(sample['pts_seconds']), '-i', str(video),
                 '-map', '0:v:0', '-frames:v', '1', '-vf',
                 f'crop={w}:{h}:{x}:{y}', '-y', str(image)], 60)
            queue.require(image.is_file() and 0 < image.stat().st_size <= 16 * 1024**2,
                          'invalid extracted image')
            found = ocr_image(image)
            image.unlink()
            if found is None:
                skipped += 1
                continue
            value, confidence = found
            observation = dict(sample, value=value, confidence=confidence,
                               engine='tesseract')
            bridge.validate_observation(observation, clips)
            observations.append(observation)
    queue.require(queue.digest(video) == video_sha, 'video changed during OCR')
    return observations, skipped, video_sha


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('plan_json')
    parser.add_argument('roi_spec_json')
    parser.add_argument('new_proposals_json')
    args = parser.parse_args(argv)
    paths = [Path(args.video), Path(args.plan_json), Path(args.roi_spec_json),
             Path(args.new_proposals_json)]
    output = paths[-1]
    queue.require(len({p.resolve() for p in paths}) == 4 and
                  output.suffix == '.json' and output.parent.is_dir() and
                  not output.parent.is_symlink() and not output.exists() and
                  not output.is_symlink(), 'output must be a distinct new JSON file')
    before = [queue.digest(p) for p in paths[1:3]]
    plan, spec = queue.read(paths[1]), queue.read(paths[2])
    observations, skipped, video_sha = build(paths[0], plan, spec)
    queue.require(before == [queue.digest(p) for p in paths[1:3]],
                  'input JSON changed during OCR')
    proposals = {'schema_version': 1, 'status': 'offline_ocr_proposals_unverified',
                 'source_plan_sha256': before[0],
                 'source_video_sha256_claim': video_sha,
                 'observations': observations}
    bridge.build(plan, proposals, before[0], '0' * 64)  # fail-closed safety check
    with output.open('x', encoding='utf-8') as stream:
        json.dump(proposals, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'samples': len(spec['samples']), 'observations': len(observations),
                      'empty_or_invalid_ocr': skipped, 'equity_hands_confirmed': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
