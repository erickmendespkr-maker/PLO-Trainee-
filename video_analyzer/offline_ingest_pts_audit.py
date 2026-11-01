"""Independent offline audit of sampled ROI evidence from offline_video_ingest_probe.

Usage: python offline_ingest_pts_audit.py VIDEO INGEST_DIR NEW_REPORT.json

Checks source/crop hashes, ROI geometry, and manifest decoded PTS against the
source's independently enumerated FFprobe frame PTS (VFR-aware). It does not
validate OCR, hands, or decisions and never authorizes equity/EV.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import re
import subprocess
from PIL import Image

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_PROBE_BYTES = 16 * 1024 * 1024
MAX_FRAMES = 250_000
MAX_SAMPLES = 512
MAX_CROP_BYTES = 8 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')
NAME = re.compile(r'table_[0-9]{2}_sample_[0-9]{3}\.jpg\Z')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        require(k not in d, 'duplicate JSON key')
        d[k] = v
    return d


def read_manifest(path):
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_JSON_BYTES, 'unsafe manifest')
    data = json.loads(path.read_text('utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    require(type(data) is dict and data.get('schema_version') == 1 and
            data.get('analysis_status') == 'offline_sampled_video_preflight_no_ocr' and
            data.get('equity_ev_computed') is False and
            data.get('hands_reconstructed') is False and
            data.get('video_evidence_interpreted') is False,
            'not an unverified offline ingest manifest')
    return data


def finite_number(x):
    return type(x) in (int, float) and math.isfinite(x)


def decoded_pts(video):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'frame=best_effort_timestamp_time',
            '-of', 'csv=p=0', str(video)], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('ffprobe unavailable or timed out') from exc
    require(result.returncode == 0 and 0 < len(result.stdout) <= MAX_PROBE_BYTES,
            'ffprobe failed or frame listing too large')
    pts = []
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        value = line.strip().rstrip(',')
        if not value or value == 'N/A':
            continue
        try:
            t = float(value)
        except ValueError as exc:
            raise ValueError('invalid FFprobe timestamp') from exc
        require(math.isfinite(t) and (not pts or t >= pts[-1]),
                'invalid or unsorted source frame PTS')
        pts.append(t)
        require(len(pts) <= MAX_FRAMES, 'source has too many frames for bounded audit')
    require(pts, 'no decoded frame timestamps')
    return pts


def materially_variable_intervals(pts):
    """Ignore small PTS tick quantization (e.g. 29.97 fps 33/34 ms)."""
    deltas = [b - a for a, b in zip(pts, pts[1:]) if b > a]
    if len(deltas) < 2:
        return False
    center = median(deltas)
    return max(deltas) - min(deltas) > max(0.005, 0.10 * center)


def closest_pts(sorted_pts, value):
    i = bisect_left(sorted_pts, value)
    candidates = []
    if i < len(sorted_pts):
        candidates.append(sorted_pts[i])
    if i:
        candidates.append(sorted_pts[i - 1])
    return min(candidates, key=lambda p: abs(p - value))


def audit(video_path, ingest_dir):
    video, folder = Path(video_path), Path(ingest_dir)
    require(video.is_file() and not video.is_symlink() and
            video.suffix.lower() in ('.mp4', '.webm', '.mov', '.mkv') and
            0 < video.stat().st_size <= 30 * 1024**3, 'unsafe video')
    require(folder.is_dir() and not folder.is_symlink() and
            video.resolve() != folder.resolve(), 'unsafe ingest directory')
    manifest = read_manifest(folder / 'manifest.json')
    require(SHA.fullmatch(str(manifest.get('source_sha256', ''))) and
            digest(video) == manifest['source_sha256'] and
            manifest.get('source_size_bytes') == video.stat().st_size,
            'source hash/size mismatch')
    regions = manifest.get('regions')
    samples = manifest.get('samples')
    media = manifest.get('media')
    require(type(media) is dict and type(regions) is list and
            1 <= len(regions) <= 4 and type(samples) is list and
            1 <= len(samples) <= MAX_SAMPLES, 'invalid regions/samples')
    width, height = media.get('width'), media.get('height')
    require(type(width) is int and type(height) is int and
            64 <= width <= 3840 and 64 <= height <= 2160,
            'invalid source geometry')
    by_id = {}
    for r in regions:
        require(type(r) is dict and set(r) ==
                {'table_id', 'x', 'y', 'width', 'height'} and
                all(type(v) is int for v in r.values()), 'invalid region')
        tid, x, y, w, h = (r[k] for k in
                            ('table_id', 'x', 'y', 'width', 'height'))
        require(1 <= tid <= 4 and tid not in by_id and
                x >= 0 and y >= 0 and w >= 64 and h >= 64 and
                x + w <= width and y + h <= height,
                'region out of bounds or duplicate')
        by_id[tid] = r
    source_pts = decoded_pts(video)
    seen, counts, last_requested = set(), {tid: 0 for tid in by_id}, {}
    verified = []
    for s in samples:
        require(type(s) is dict and s.get('table_id') in by_id and
                type(s['table_id']) is int, 'invalid table reference')
        tid = s['table_id']
        name = s.get('file')
        require(type(name) is str and NAME.fullmatch(name) and
                name.startswith(f'table_{tid:02d}_') and name not in seen,
                'unsafe/duplicate sample path')
        seen.add(name)
        requested = s.get('timestamp_seconds')
        actual = s.get('actual_frame_timestamp_seconds')
        require(finite_number(requested) and finite_number(actual) and
                requested >= 0 and (tid not in last_requested or
                requested > last_requested[tid]), 'invalid/unsorted requested time')
        last_requested[tid] = requested
        require(SHA.fullmatch(str(s.get('sha256', ''))), 'invalid crop SHA')
        crop = folder / name
        require(crop.is_file() and not crop.is_symlink() and
                0 < crop.stat().st_size <= MAX_CROP_BYTES and
                digest(crop) == s['sha256'], 'missing/adulterated crop')
        with Image.open(crop) as img:
            require(img.format == 'JPEG' and img.size ==
                    (by_id[tid]['width'], by_id[tid]['height']),
                    'incorrect crop format/dimensions')
            img.verify()
        nearest = closest_pts(source_pts, actual)
        require(abs(nearest - actual) <= 0.002,
                'manifest decoded PTS absent from source frames')
        counts[tid] += 1
        verified.append({'table_id': tid, 'file': name,
                         'requested_seconds': requested,
                         'manifest_decoded_pts_seconds': actual,
                         'independent_ffprobe_pts_seconds': nearest,
                         'requested_to_decoded_delta_seconds': round(actual - requested, 6),
                         'crop_sha256_verified': True})
    require(all(counts.values()) and len(set(counts.values())) == 1,
            'missing samples for one or more tables')
    require(digest(video) == manifest['source_sha256'], 'source changed during audit')
    vfr = materially_variable_intervals(source_pts)
    return {'schema_version': 1,
            'status': 'offline_ingest_pts_and_crop_provenance_audited_not_ocr',
            'source_sha256': manifest['source_sha256'],
            'table_count': len(by_id), 'sample_count': len(verified),
            'source_decoded_frame_count': len(source_pts),
            'variable_frame_intervals_observed': vfr,
            'max_abs_requested_to_decoded_delta_seconds':
                max(round(abs(x['requested_to_decoded_delta_seconds']), 6) for x in verified),
            'verified_samples': verified,
            'ocr_verified': False, 'hands_reconstructed': False,
            'equity_ev_authorized': False,
            'limitations': [
                'Checks FFprobe timestamps and JPEG dimensions/hashes, not card/action content.',
                'Frame PTS is decoder evidence, not human-labeled ground truth.',
                'Sparse samples may miss hand transitions; real video accuracy is unmeasured.',
                'Full-frame FFprobe enumeration is bounded and may reject large/high-FPS recordings.']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('recording')
    p.add_argument('ingest_directory')
    p.add_argument('new_report_json')
    a = p.parse_args(argv)
    output = Path(a.new_report_json)
    require(output.suffix == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists() and
            not output.is_symlink(), 'report must be a new JSON file')
    result = audit(a.recording, a.ingest_directory)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    print(json.dumps({'tables': result['table_count'],
                      'verified_samples': result['sample_count'],
                      'vfr_observed': result['variable_frame_intervals_observed']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
