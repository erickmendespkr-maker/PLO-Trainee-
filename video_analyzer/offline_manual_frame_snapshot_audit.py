"""Audit human-declared card timestamps against a local clip by extracting PNGs.

Usage: python offline_manual_frame_snapshot_audit.py BINDING CLIP REVIEW NEW_DIRECTORY

This proves that PNGs came from the clip identified by the reviewed hashes, NOT
that any card is visible or recognized correctly. Requested timestamps are not
asserted to equal the exact presentation timestamps of decoded frames.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from offline_plo_equity_monte_carlo import cards, read_json, require
from offline_reviewed_equity_clip_report import (
    REVIEW_FIELDS, REQUIRED, check_binding, digest, safe_file,
)


def command(argv, timeout=30):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'local media tool failed: {type(exc).__name__}') from exc
    require(proc.returncode == 0, 'local media tool returned an error')
    return proc.stdout


def probe(clip):
    raw = command(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                   '-show_entries', 'stream=codec_type,width,height:format=duration',
                   '-of', 'json', str(clip)])
    try:
        obj = json.loads(raw)
        streams = obj['streams']
        duration = float(obj['format']['duration'])
        stream = streams[0]
        width, height = stream['width'], stream['height']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError('invalid video metadata') from exc
    require(stream.get('codec_type') == 'video' and
            type(width) is int and type(height) is int and
            1 <= width <= 8192 and 1 <= height <= 8192 and
            math.isfinite(duration) and 0 < duration <= 4 * 3600,
            'invalid video geometry or duration')
    return duration, width, height


def validate(binding, review, binding_hash, clip_hash, duration):
    check_binding(binding)
    require(binding['clip_sha256'] == clip_hash, 'clip differs from evidence binding')
    require(type(review) is dict and REQUIRED <= set(review) <= REVIEW_FIELDS and
            review.get('schema_version') == 1 and
            type(review.get('schema_version')) is int, 'invalid review schema')
    require(type(review.get('review_notes')) is str and
            8 <= len(review['review_notes'].strip()) <= 2000,
            'review notes required')
    require(review.get('source_binding_sha256') == binding_hash and
            review.get('source_clip_sha256') == clip_hash, 'review source hash mismatch')
    for key in ('hand_id', 'table_id', 'proposal_index', 'variant'):
        require(type(review.get(key)) is type(binding[key]) and review[key] == binding[key],
                'review identity mismatch: ' + key)
    require(review.get('manual_cards_confirmed') is True and
            review.get('review_method') == 'manual_video_frame_review',
            'human review assertion required')
    n = 5 if binding['variant'] == 'PLO5' else 6
    hero = cards(review.get('hero_cards'), n)
    board = cards(review.get('board_cards'))
    require(3 <= len(board) <= 5 and len(set(hero + board)) == len(hero) + len(board),
            'invalid or overlapping reviewed cards')
    evidence = review.get('card_frame_evidence')
    require(type(evidence) is list and len(evidence) == len(hero) + len(board),
            'one card/frame entry required per card')
    seen = set()
    timestamps = []
    for entry in evidence:
        require(type(entry) is dict and set(entry) == {'card', 'clip_timestamp_seconds'},
                'invalid card/frame entry')
        card, stamp = entry['card'], entry['clip_timestamp_seconds']
        require(type(card) is str and card in hero + board and card not in seen,
                'unknown or duplicate evidence card')
        require(type(stamp) in (int, float) and math.isfinite(stamp) and
                0 <= stamp < duration, 'declared timestamp outside clip')
        seen.add(card)
        timestamps.append(float(stamp))
    require(seen == set(hero + board), 'missing card/frame evidence')
    return evidence, timestamps


def build(binding_path, clip_path, review_path, new_directory):
    paths = [safe_file(binding_path, max_bytes=2_000_000), safe_file(clip_path),
             safe_file(review_path, max_bytes=2_000_000)]
    require(len({p.resolve() for p in paths}) == 3, 'source files must differ')
    target = Path(new_directory)
    require(target.parent.is_dir() and not target.parent.is_symlink() and
            not target.exists() and not target.is_symlink(), 'output must be a new directory')
    require(target.resolve() not in {p.resolve() for p in paths}, 'output overlaps input')
    fingerprints = [digest(p) for p in paths]
    binding, review = read_json(paths[0]), read_json(paths[2])
    duration, width, height = probe(paths[1])
    evidence, stamps = validate(binding, review, fingerprints[0], fingerprints[1], duration)
    temp = Path(tempfile.mkdtemp(prefix='.plo_frame_audit_', dir=target.parent))
    try:
        frames = []
        index_by_stamp = {}
        for stamp in stamps:
            if stamp in index_by_stamp:
                continue
            idx = len(frames)
            name = f'frame_{idx:02d}.png'
            png = temp / name
            # Accurate seek is performed after input decoding. The requested time
            # is recorded; decoded frame presentation time is not independently proven.
            command(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                     '-threads', '1', '-i', str(paths[1]), '-ss', format(stamp, '.9f'),
                     '-frames:v', '1', '-an', '-sn', '-f', 'image2', '-vcodec', 'png',
                     str(png)], timeout=90)
            require(png.is_file() and not png.is_symlink() and
                    0 < png.stat().st_size <= 50_000_000, 'frame extraction failed')
            index_by_stamp[stamp] = name
            frames.append({'file': name, 'requested_clip_timestamp_seconds': stamp,
                           'sha256': digest(png)})
        card_map = [{'card': item['card'],
                     'requested_clip_timestamp_seconds': float(item['clip_timestamp_seconds']),
                     'frame_file': index_by_stamp[float(item['clip_timestamp_seconds'])]}
                    for item in evidence]
        require(all(digest(p) == h for p, h in zip(paths, fingerprints)),
                'source changed during extraction')
        manifest = {
            'schema_version': 1,
            'analysis_status': 'manual_timestamp_frame_extraction_only',
            'source_binding_sha256': fingerprints[0],
            'source_clip_sha256': fingerprints[1],
            'source_manual_review_sha256': fingerprints[2],
            'hand_id': binding['hand_id'], 'table_id': binding['table_id'],
            'variant': binding['variant'], 'proposal_index': binding['proposal_index'],
            'clip_duration_seconds': duration, 'clip_width': width, 'clip_height': height,
            'frames': frames, 'card_frame_links': card_map,
            'extracted_from_reviewed_clip': True,
            'exact_decoded_frame_timestamp_verified': False,
            'card_visibility_verified': False, 'ocr_semantics_verified': False,
            'player_identity_verified': False, 'strategic_correctness_verified': False,
            'warning': ('PNG hashes prove local extraction from the hash-matched clip. '
                        'Card labels/timestamps are human assertions, not visual verification; '
                        'requested timestamps are not decoded-frame PTS measurements.'),
        }
        (temp / 'manifest.json').write_text(json.dumps(manifest, indent=2,
                                                       ensure_ascii=False, allow_nan=False) + '\n',
                                             encoding='utf-8')
        require(not target.exists(), 'output appeared during extraction')
        temp.rename(target)
        return manifest
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('binding_json', 'clip_mp4', 'manual_review_json', 'new_directory'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    result = build(args.binding_json, args.clip_mp4, args.manual_review_json,
                   args.new_directory)
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'frames': len(result['frames']),
                      'cards': len(result['card_frame_links'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
