"""Fail-closed, offline, manually selected multi-table MP4 clip batch exporter.

Usage: python offline_reviewed_clip_batch.py RECORDING.mp4 MANIFEST.json NEW_DIRECTORY

No OCR assertions, automatic selection, EV claims, live poker, or credentials.
The manifest contains single-clip request objects in ``clips``. The entire
output directory is published only after all clips and sidecars are checked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import offline_reviewed_clip_export as single

MAX_MANIFEST_BYTES = 128 * 1024
MAX_CLIPS = 12
MAX_TOTAL_SECONDS = 900.0
ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def read_manifest(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= MAX_MANIFEST_BYTES, 'Invalid manifest file')
    return json.loads(p.read_text(encoding='utf-8'),
                      object_pairs_hook=single._unique_keys,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def validate_manifest(raw, width, height, duration, video_sha):
    require(type(raw) is dict and set(raw) == {
        'schema_version', 'source_video_sha256', 'reviewer_confirmed_offline',
        'reviewer_note', 'clips'}, 'Invalid batch manifest schema')
    require(type(raw['schema_version']) is int and raw['schema_version'] == 1,
            'Unsupported batch schema')
    require(raw['reviewer_confirmed_offline'] is True and
            type(raw['reviewer_note']) is str and
            1 <= len(raw['reviewer_note'].strip()) <= 1000,
            'Human approval and reviewer note required')
    require(type(raw['source_video_sha256']) is str and
            SHA_RE.fullmatch(raw['source_video_sha256']) and
            raw['source_video_sha256'] == video_sha,
            'Recording SHA-256 mismatch')
    clips = raw['clips']
    require(type(clips) is list and 1 <= len(clips) <= MAX_CLIPS,
            'Invalid clip count')
    seen, windows = set(), {}
    total = 0.0
    for idx, req in enumerate(clips):
        single.validate_request(req, width, height, duration, video_sha)
        hand_id, table_id = req['hand_id'], req['table_id']
        require(ID_RE.fullmatch(hand_id) is not None,
                'Hand ID must be a safe filename component')
        require((table_id, hand_id) not in seen, 'Duplicate hand/table selection')
        seen.add((table_id, hand_id))
        require(req['reviewer_confirmed_offline'] is True,
                'Every clip must be individually approved')
        start, end = float(req['start_seconds']), float(req['end_seconds'])
        require(math.isfinite(start) and math.isfinite(end), 'Non-finite timestamps')
        total += end - start
        require(total <= MAX_TOTAL_SECONDS, 'Excessive aggregate clip duration')
        windows.setdefault(table_id, []).append((start, end, idx))
    # Different tables may legitimately overlap in the same four-table video.
    for intervals in windows.values():
        ordered = sorted(intervals)
        for (_, previous_end, _), (start, _, _) in zip(ordered, ordered[1:]):
            require(start >= previous_end, 'Overlapping selections on the same table')
    return clips, total


def export_batch(video_path, manifest_path, output_directory):
    video, manifest, dest = map(Path, (video_path, manifest_path, output_directory))
    require(video.is_file() and not video.is_symlink() and
            video.suffix.lower() in ('.mp4', '.webm') and
            0 < video.stat().st_size <= single.MAX_VIDEO_BYTES,
            'Invalid offline recording')
    require(manifest.is_file() and not manifest.is_symlink(), 'Invalid manifest')
    require(dest.parent.is_dir() and not dest.parent.is_symlink() and
            not dest.exists() and not dest.is_symlink() and
            dest.name not in ('.', '..') and
            dest.resolve() not in (video.resolve(), manifest.resolve()),
            'Output directory must be new and separate')
    video_sha, manifest_sha = single.digest(video), single.digest(manifest)
    raw = read_manifest(manifest)
    width, height, duration = single.probe(video)
    requests, total = validate_manifest(raw, width, height, duration, video_sha)
    with tempfile.TemporaryDirectory(prefix='plo_batch_', dir=dest.parent) as tmp:
        stage = Path(tmp) / 'clips'
        stage.mkdir()
        entries = []
        for idx, req in enumerate(requests, 1):
            # Deterministic, safe names: no user-supplied path is used.
            filename = f'{idx:02d}_table{req["table_id"]}_{req["hand_id"]}.mp4'
            request_file = stage / f'{idx:02d}_request.json'
            request_file.write_text(json.dumps(req, ensure_ascii=False, allow_nan=False) + '\n',
                                    encoding='utf-8')
            clip_path = stage / filename
            metadata = single.export(video, request_file, clip_path)
            require(metadata['clip_sha256'] == single.digest(clip_path) and
                    metadata['source_video_sha256'] == video_sha and
                    metadata['hand_id'] == req['hand_id'] and
                    metadata['table_id'] == req['table_id'],
                    'Clip provenance verification failed')
            # Preserve the exact validated single-clip request in the batch directory.
            entries.append({'hand_id': req['hand_id'], 'table_id': req['table_id'],
                            'clip_file': filename, 'sidecar_file': filename + '.json',
                            'request_file': request_file.name,
                            'clip_sha256': metadata['clip_sha256'],
                            'request_sha256': single.digest(request_file),
                            'start_seconds': req['start_seconds'],
                            'end_seconds': req['end_seconds']})
        require(single.digest(video) == video_sha and
                single.digest(manifest) == manifest_sha,
                'Recording or manifest changed during batch export')
        report = {
            'schema_version': 1,
            'analysis_status': 'manually_selected_offline_clip_batch_only',
            'source_video_sha256': video_sha,
            'source_manifest_sha256': manifest_sha,
            'clip_count': len(entries), 'aggregate_selected_seconds': round(total, 6),
            'clips': entries, 'reviewer_note': raw['reviewer_note'],
            'audio_included': False, 'video_evidence_verified': False,
            'complete_hands_reconstructed': False,
            'automatic_clip_selection_authorized': False,
            'action_recommendation_authorized': False,
            'warning': 'Manually supplied timestamps, crops and explanations; no independent poker hand or EV verification.'
        }
        (stage / 'batch_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        # An atomic rename publishes either a complete batch or no batch.
        require(not dest.exists() and not dest.is_symlink(), 'Destination appeared during export')
        os.rename(stage, dest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('manifest')
    parser.add_argument('new_directory')
    args = parser.parse_args(argv)
    result = export_batch(args.video, args.manifest, args.new_directory)
    print(json.dumps({'status': result['analysis_status'], 'clips': result['clip_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
