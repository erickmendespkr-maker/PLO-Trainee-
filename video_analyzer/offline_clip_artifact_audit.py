"""Read-only integrity audit for an offline reviewed-clip pipeline bundle.

Usage: python offline_clip_artifact_audit.py BUNDLE_DIR [--source-video VIDEO]

Checks SHA-256 chains, consistent IDs/timestamps/crop, FFprobe dimensions,
duration and absence of audio. It does NOT verify OCR, poker actions, ranges,
equity, EV, or whether the chosen interval contains a real hand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

HEX = re.compile(r'[0-9a-f]{64}\Z')
FILES = ('manifest.json', 'gate/request.json', 'gate/provenance.json',
         'clip.mp4', 'clip.mp4.json')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    need(0 < path.stat().st_size <= 1024 * 1024, 'invalid JSON size')
    obj = json.loads(path.read_text('utf-8'), object_pairs_hook=unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    need(type(obj) is dict, 'expected JSON object')
    return obj


def same_hash(obj, key, actual):
    value = obj.get(key)
    need(type(value) is str and HEX.fullmatch(value) is not None
         and value == actual, 'hash mismatch: ' + key)


def probe_clip(path):
    try:
        proc = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                               'format=duration:stream=codec_type,width,height',
                               '-of', 'json', str(path)], capture_output=True,
                              text=True, check=True, timeout=30)
        obj = json.loads(proc.stdout)
        streams = obj['streams']
        videos = [x for x in streams if x.get('codec_type') == 'video']
        duration = float(obj['format']['duration'])
        need(len(videos) == 1 and all(x.get('codec_type') != 'audio' for x in streams),
             'clip stream mismatch')
        w, h = videos[0]['width'], videos[0]['height']
        need(type(w) is int and type(h) is int and w >= 2 and h >= 2
             and math.isfinite(duration) and duration > 0, 'invalid clip media')
        return w, h, duration
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('FFprobe failed or invalid clip') from exc


def audit(bundle_dir, source_video=None):
    root = Path(bundle_dir)
    need(root.is_dir() and not root.is_symlink(), 'invalid bundle directory')
    files = {name: root / name for name in FILES}
    need((root / 'gate').is_dir() and not (root / 'gate').is_symlink(),
         'unsafe gate directory')
    for name, path in files.items():
        need(path.is_file() and not path.is_symlink(), 'missing or unsafe file: ' + name)
    m, r, p, sidecar = (read_json(files[name]) for name in
                        ('manifest.json', 'gate/request.json', 'gate/provenance.json',
                         'clip.mp4.json'))
    need(m.get('schema_version') == 1 and
         m.get('analysis_status') == 'offline_reviewed_clip_pipeline_evidence_only'
         and p.get('analysis_status') == 'offline_clip_review_gate_only'
         and sidecar.get('analysis_status') == 'manually_selected_offline_clip'
         and r.get('schema_version') == 1, 'unexpected bundle schema/status')
    for obj, fields in (
        (m, ('hands_reconstructed', 'ready_for_equity_or_ev',
             'source_video_matches_ocr_source_verified')),
        (p, ('hands_reconstructed', 'ready_for_equity_or_ev',
             'source_video_matches_ocr_source_verified')),
        (sidecar, ('video_evidence_verified', 'automatic_clip_selection_authorized',
                   'audio_included')),
    ):
        need(all(obj.get(field) is False for field in fields),
             'unverified analysis claimed as verified')
    need(r.get('reviewer_confirmed_offline') is True, 'manual approval missing')
    need(type(r.get('hand_id')) is str and r['hand_id']
         and type(r.get('table_id')) is int and 1 <= r['table_id'] <= 4,
         'invalid hand/table')
    need(all(obj.get('hand_id') == r['hand_id'] and
             obj.get('table_id') == r['table_id'] for obj in (m, p, sidecar)),
         'hand/table provenance mismatch')
    for key in ('source_video_sha256',):
        value = r.get(key)
        need(type(value) is str and HEX.fullmatch(value) is not None
             and all(obj.get(key) == value for obj in (m, p, sidecar)),
             'source video identity mismatch')
    same_hash(m, 'gate_request_sha256', digest(files['gate/request.json']))
    same_hash(m, 'gate_provenance_sha256', digest(files['gate/provenance.json']))
    same_hash(m, 'clip_sha256', digest(files['clip.mp4']))
    same_hash(m, 'clip_sidecar_sha256', digest(files['clip.mp4.json']))
    same_hash(sidecar, 'source_request_sha256', digest(files['gate/request.json']))
    same_hash(sidecar, 'clip_sha256', digest(files['clip.mp4']))
    need(sidecar.get('crop') == r.get('crop') and
         sidecar.get('start_seconds') == r.get('start_seconds') and
         sidecar.get('end_seconds') == r.get('end_seconds'),
         'clip/request interval or crop mismatch')
    crop = r.get('crop')
    need(type(crop) is dict and set(crop) == {'x', 'y', 'width', 'height'}
         and all(type(v) is int and v >= 0 and v % 2 == 0 for v in crop.values())
         and crop['width'] >= 2 and crop['height'] >= 2, 'invalid crop')
    start, end = r.get('start_seconds'), r.get('end_seconds')
    need(all(type(v) in (int, float) and math.isfinite(v) for v in (start, end))
         and 0 <= start < end and .1 <= end - start <= 180,
         'invalid requested interval')
    width, height, duration = probe_clip(files['clip.mp4'])
    need((width, height) == (crop['width'], crop['height'])
         and m.get('clip_dimensions') == {'width': width, 'height': height}
         and type(m.get('clip_duration_seconds')) in (int, float)
         and abs(m['clip_duration_seconds'] - duration) <= .001
         and abs(duration - (end - start)) <= .25, 'clip media mismatch')
    source_checked = source_video is not None
    if source_checked:
        src = Path(source_video)
        need(src.is_file() and not src.is_symlink(), 'unsafe source video')
        same_hash(r, 'source_video_sha256', digest(src))
    return {'schema_version': 1, 'audit_status': 'bundle_integrity_verified_only',
            'hand_id': r['hand_id'], 'table_id': r['table_id'],
            'clip_sha256': digest(files['clip.mp4']),
            'source_video_hash_checked': source_checked,
            'source_video_matches_ocr_source_verified': False,
            'ready_for_equity_or_ev': False,
            'warning': 'Hash consistency is not validation of poker observations.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle_dir')
    parser.add_argument('--source-video')
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.bundle_dir, args.source_video)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
