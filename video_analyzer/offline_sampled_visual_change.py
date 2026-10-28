"""Conservative offline visual-change triage for sampled table-region JPG evidence.

Consumes the immutable manifest from offline_video_ingest_probe.py. Visual changes
are NOT poker hand boundaries: this module never identifies cards, actions or EV.
Usage: python offline_sampled_visual_change.py INGEST_DIR NEW_OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

SIDE = 32
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 12 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_manifest(ingest_dir):
    path = ingest_dir / 'manifest.json'
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_MANIFEST_BYTES, 'Invalid ingest manifest')
    try:
        manifest = json.loads(path.read_text('utf-8'), object_pairs_hook=unique_keys,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Malformed ingest manifest') from exc
    require(type(manifest) is dict and type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1 and
            manifest.get('analysis_status') == 'offline_sampled_video_preflight_no_ocr' and
            type(manifest.get('media')) is dict and
            type(manifest.get('regions')) is list and
            type(manifest.get('samples')) is list,
            'Unexpected ingest schema')
    require(all(type(manifest.get(k)) is str and re.fullmatch('[0-9a-f]{64}', manifest[k])
                for k in ('source_sha256', 'regions_config_sha256')),
            'Invalid source identity')
    duration = manifest['media'].get('duration_seconds')
    require(type(duration) in (int, float) and math.isfinite(duration) and
            0.5 <= duration <= 3600, 'Invalid media duration')
    ids = [r.get('table_id') for r in manifest['regions'] if type(r) is dict]
    require(1 <= len(ids) <= 4 and len(set(ids)) == len(ids) and
            all(type(i) is int and 1 <= i <= 4 for i in ids), 'Invalid table IDs')
    require(len(manifest['samples']) <= 4 * 800, 'Too many sampled frames')
    return manifest, sha256(path)


def decode_gray(path):
    """FFmpeg returns a fixed 32x32 grayscale representation (no OCR)."""
    try:
        proc = subprocess.run(
            ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-threads', '1',
             '-i', str(path), '-vf', f'scale={SIDE}:{SIDE}:flags=area,format=gray',
             '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'],
            capture_output=True, check=False, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Could not decode sampled frame') from exc
    require(proc.returncode == 0 and len(proc.stdout) == SIDE * SIDE,
            'Invalid sampled image or decoded size')
    return proc.stdout


def frame_records(ingest_dir, manifest):
    ids = {r['table_id'] for r in manifest['regions']}
    grouped = {table_id: [] for table_id in sorted(ids)}
    names = set()
    for sample in manifest['samples']:
        require(type(sample) is dict, 'Invalid sample entry')
        table_id = sample.get('table_id')
        name = sample.get('file')
        pts = sample.get('actual_frame_timestamp_seconds')
        requested = sample.get('timestamp_seconds')
        digest = sample.get('sha256')
        require(type(table_id) is int and table_id in ids and
                type(name) is str and re.fullmatch(r'table_\d{2}_sample_\d{3}\.jpg', name) and
                name not in names and name.startswith(f'table_{table_id:02d}_') and
                type(pts) in (int, float) and math.isfinite(pts) and
                -0.05 <= pts <= manifest['media']['duration_seconds'] + 0.1 and
                type(requested) in (int, float) and math.isfinite(requested) and
                type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest),
                'Invalid sample identity, timestamp or hash')
        names.add(name)
        path = ingest_dir / name
        require(path.is_file() and not path.is_symlink() and
                0 < path.stat().st_size <= MAX_FRAME_BYTES and
                sha256(path) == digest, 'Sample missing, unsafe or modified')
        grouped[table_id].append({'pts': float(pts), 'requested': float(requested),
                                  'file': name, 'sha256': digest, 'path': path})
    require(all(grouped.values()), 'Missing table samples')
    for records in grouped.values():
        records.sort(key=lambda x: (x['pts'], x['requested'], x['file']))
    return grouped


def compare_frames(previous, current):
    require(len(previous) == len(current) == SIDE * SIDE, 'Unexpected frame size')
    deltas = [abs(a - b) for a, b in zip(previous, current)]
    return (round(sum(deltas) / (len(deltas) * 255), 6),
            round(sum(delta >= 26 for delta in deltas) / len(deltas), 6))


def analyze(ingest_dir, output_dir, threshold=0.12, min_coverage=0.20,
            max_gap_seconds=10.0):
    ingest_dir, output_dir = Path(ingest_dir), Path(output_dir)
    require(ingest_dir.is_dir() and not ingest_dir.is_symlink(), 'Invalid ingest directory')
    require(output_dir.parent.is_dir() and not output_dir.exists() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name) and
            output_dir.resolve() != ingest_dir.resolve(), 'Output must be a new safe directory')
    require(all(type(x) in (int, float) and math.isfinite(x) for x in
                (threshold, min_coverage, max_gap_seconds)) and
            0.01 <= threshold <= 0.9 and 0 <= min_coverage <= 1 and
            0.5 <= max_gap_seconds <= 600, 'Invalid detector parameters')
    manifest, manifest_hash = read_manifest(ingest_dir)
    grouped = frame_records(ingest_dir, manifest)
    events, diagnostics = [], []
    for table_id, records in grouped.items():
        previous, previous_gray = None, None
        for record in records:
            gray = decode_gray(record['path'])
            if previous is not None:
                gap = round(record['pts'] - previous['pts'], 6)
                if gap <= 0:
                    diagnostics.append({'table_id': table_id, 'file': record['file'],
                                        'reason': 'duplicate_or_nonincreasing_decoded_pts'})
                else:
                    difference, coverage = compare_frames(previous_gray, gray)
                    if difference >= threshold and coverage >= min_coverage:
                        events.append({
                            'table_id': table_id, 'earliest_possible_change_seconds': previous['pts'],
                            'latest_possible_change_seconds': record['pts'],
                            'gap_seconds': gap, 'sparse_evidence': gap > max_gap_seconds,
                            'mean_absolute_grayscale_difference': difference,
                            'changed_pixel_fraction': coverage,
                            'previous_file': previous['file'], 'current_file': record['file'],
                            'classification': 'unlocalized_visual_change_for_manual_review',
                            'hand_boundary_confidence': None,
                            'visual_signal_strength_uncalibrated': round(min(1.0, difference / threshold), 3)
                        })
            previous, previous_gray = record, gray
    events.sort(key=lambda e: (e['earliest_possible_change_seconds'], e['table_id']))
    report = {
        'schema_version': 1, 'analysis_status': 'offline_visual_change_candidates_only',
        'ingest_manifest_sha256': manifest_hash, 'source_sha256': manifest['source_sha256'],
        'regions_config_sha256': manifest['regions_config_sha256'],
        'table_count': len(grouped), 'sample_count': sum(map(len, grouped.values())),
        'detector': {'name': 'downsampled_grayscale_mean_absolute_difference',
                     'image_side': SIDE, 'threshold': threshold,
                     'minimum_changed_pixel_fraction': min_coverage,
                     'max_dense_gap_seconds': max_gap_seconds},
        'candidate_intervals': events, 'diagnostics': diagnostics,
        'hands_reconstructed': False, 'hand_boundaries_verified': False,
        'ocr_performed': False, 'equity_ev_computed': False,
        'warning': 'Mudancas visuais nao comprovam inicio/fim de maos; intervalos exigem revisao humana.'
    }
    with tempfile.TemporaryDirectory(prefix='.plo_change_', dir=output_dir.parent) as tmp:
        stage = Path(tmp)
        (stage / 'visual_changes.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', 'utf-8')
        require(sha256(ingest_dir / 'manifest.json') == manifest_hash,
                'Ingest manifest changed during analysis')
        require(not output_dir.exists(), 'Output path appeared during processing')
        os.rename(stage, output_dir)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ingest_dir')
    parser.add_argument('new_output_dir')
    parser.add_argument('--threshold', type=float, default=0.12)
    parser.add_argument('--min-coverage', type=float, default=0.20)
    parser.add_argument('--max-gap-seconds', type=float, default=10.0)
    args = parser.parse_args(argv)
    result = analyze(args.ingest_dir, args.new_output_dir, args.threshold,
                     args.min_coverage, args.max_gap_seconds)
    print(json.dumps({'samples': result['sample_count'],
                      'candidates': len(result['candidate_intervals'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
