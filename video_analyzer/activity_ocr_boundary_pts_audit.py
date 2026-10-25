"""Offline decoded-PTS audit for Cycle 83 OCR hand-boundary navigation PNGs.

A matching re-decode proves only the filtergraph PTS of that PNG. It never
verifies a hand boundary, a card, a bet, or the correctness of any strategy.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from activity_math_review_pts_audit import _parse_decoded_pts
from activity_ocr_boundary_visual_evidence import build_boundary_visual_plan

STATUS = 'ocr_boundary_navigation_decoded_pts_audit_only'
HEX = re.compile(r'[0-9a-f]{64}\Z')
NAME = re.compile(r'table_(0[1-4])_seek_([0-9]{4})\.png\Z')


def _regular(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('Expected regular non-symlink file')
    return p


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def audit_ocr_boundary_pts(video_path, temporal_json, boundary_json, evidence_dir,
                           output_dir, *, regions_json=None):
    """Recompute provenance and re-decode each PNG; publish a new audit only.

    The same pre-input seek and optional crop as the original extractor are
    used. ``-copyts`` plus ``showinfo`` exposes source-filtergraph PTS, while
    PNG byte identity gates any association of that PTS with the old still.
    """
    video, temporal, boundary = map(_regular, (video_path, temporal_json, boundary_json))
    evidence, output = Path(evidence_dir), Path(output_dir)
    if (evidence.is_symlink() or not evidence.is_dir() or output.exists()
            or output.is_symlink() or output.resolve().is_relative_to(evidence.resolve())):
        raise ValueError('Require existing real evidence directory and new output outside it')
    manifest_path = _regular(evidence / 'boundary_visual_evidence.json')
    regions = _regular(regions_json) if regions_json is not None else None
    inputs = [video, temporal, boundary, manifest_path] + ([regions] if regions else [])
    if len({p.resolve() for p in inputs}) != len(inputs):
        raise ValueError('Input files must be distinct')
    hashes = [_sha(p) for p in inputs]
    report = _read(manifest_path)
    if not isinstance(report, dict) or not isinstance(report.get('frames'), list):
        raise ValueError('Invalid evidence manifest')
    count = report.get('counts', {}).get('frames_planned')
    if type(count) is not int or not 0 <= count <= 120 or len(report['frames']) != count:
        raise ValueError('Invalid frame budget or count')
    # Reconstruct every authoritative planning field from original inputs.
    # The Cycle 83 manifest does not store samples_per_window or max_frames.
    # Infer them only through exact equality with a recomputed bounded plan.
    baseline = None
    for samples in (1, 2, 3):
        trial = build_boundary_visual_plan(
            video, _read(temporal), _read(boundary), temporal_sha256=hashes[1],
            max_frames=max(1, count), samples_per_window=samples,
            table_regions=_read(regions) if regions else None)
        if _plan_matches(report, trial, hashes, regions):
            baseline = trial
            break
    if baseline is None:
        raise ValueError('Evidence manifest does not match recomputed plan')
    stills = []
    for i, frame in enumerate(report['frames']):
        if not isinstance(frame, dict) or set(frame) != set(baseline['frames'][i]):
            raise ValueError('Unexpected evidence frame fields')
        name, sha = frame['filename'], frame['sha256']
        match = NAME.fullmatch(name) if isinstance(name, str) else None
        if (match is None or int(match.group(1)) != frame['table_id']
                or int(match.group(2)) != frame['frame_id']
                or not isinstance(sha, str) or HEX.fullmatch(sha) is None
                or frame['status'] != 'navigation_png_extracted_not_pts_audited'
                or frame['decoded_pts_seconds'] is not None
                or frame['decoded_pts_verified'] is not False):
            raise ValueError('Invalid or falsely verified navigation PNG metadata')
        still = _regular(evidence / name)
        if _sha(still) != sha:
            raise ValueError('Navigation PNG SHA-256 mismatch')
        stills.append(still)
    if {p.name for p in evidence.glob('*.png')} != {p.name for p in stills}:
        raise ValueError('Unexpected or missing navigation PNG')
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='.plo_boundary_pts_', dir=output.parent) as temp:
        stage = Path(temp)
        for frame, still in zip(report['frames'], stills):
            new_png = stage / frame['filename']
            filters = ['showinfo']
            if frame['region'] is not None:
                rect = frame['region']
                filters.append('crop={width}:{height}:{x}:{y}'.format(**rect))
            cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info',
                   '-copyts', '-ss', str(frame['requested_seek_seconds']),
                   '-i', str(video), '-vf', ','.join(filters),
                   '-frames:v', '1', '-update', '1', '-y', str(new_png)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            ticks, seconds, timebase = _parse_decoded_pts(result.stderr)
            if not new_png.is_file() or new_png.stat().st_size < 100:
                raise ValueError('Re-decoding did not produce a valid PNG')
            new_hash = _sha(new_png)
            matched = new_hash == frame['sha256']
            rows.append({
                'frame_id': frame['frame_id'], 'table_id': frame['table_id'],
                'filename': frame['filename'], 'requested_seek_seconds': frame['requested_seek_seconds'],
                'source_png_sha256': frame['sha256'], 'redecoded_png_sha256': new_hash,
                'png_bytes_match': matched,
                'decoded_pts_seconds': seconds if matched else None,
                'decoded_pts_ticks': ticks if matched else None,
                'decoded_pts_time_base': timebase if matched else None,
                'requested_to_decoded_delta_seconds':
                    seconds - frame['requested_seek_seconds'] if matched else None,
                'timestamp_semantics': ('ffmpeg_filtergraph_pts_not_wall_clock' if matched
                                        else 'unverified_due_to_png_mismatch'),
            })
        if any(_sha(p) != sha for p, sha in zip(inputs, hashes)):
            raise ValueError('Source changed during audit')
        if any(_sha(p) != f['sha256'] for p, f in zip(stills, report['frames'])):
            raise ValueError('Navigation PNG changed during audit')
        result = {
            'schema_version': 1, 'analysis_status': STATUS,
            'recording_sha256': hashes[0],
            'source_boundary_visual_manifest_sha256': hashes[3],
            'source_temporal_report_sha256': hashes[1],
            'source_boundary_report_sha256': hashes[2],
            'source_regions_json_sha256': hashes[4] if regions else None,
            'frames': rows,
            'counts': {'frames_checked': len(rows),
                       'byte_identical_decodes': sum(r['png_bytes_match'] for r in rows),
                       'unverified_pts': sum(not r['png_bytes_match'] for r in rows)},
            'requires_manual_review': True, 'hand_boundaries_verified': False,
            'cards_or_actions_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': ('Matching PNG establishes decoded FFmpeg filtergraph PTS only; '
                        'OCR transitions remain hypotheses requiring manual review.'),
        }
        (stage / 'boundary_pts_audit.json').write_text(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
            encoding='utf-8')
        output.mkdir(exist_ok=False)
        try:
            os.link(stage / 'boundary_pts_audit.json', output / 'boundary_pts_audit.json')
        except BaseException:
            shutil.rmtree(output)
            raise
    return result


def _plan_matches(report, baseline, hashes, regions):
    if (report.get('source_boundary_report_sha256') != hashes[2]
            or report.get('source_regions_json_sha256') != (hashes[4] if regions else None)):
        return False
    if not isinstance(report.get('frames'), list) or len(report['frames']) != len(baseline['frames']):
        return False
    stripped = dict(report)
    stripped['frames'] = []
    for actual, expected in zip(report['frames'], baseline['frames']):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            return False
        stripped['frames'].append({**actual, 'sha256': None, 'status': 'planned_not_decoded'})
    return stripped == {**baseline, 'source_boundary_report_sha256': hashes[2],
                        'source_regions_json_sha256': hashes[4] if regions else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('temporal_json')
    parser.add_argument('boundary_json')
    parser.add_argument('evidence_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--regions-json')
    args = parser.parse_args(argv)
    result = audit_ocr_boundary_pts(args.video, args.temporal_json, args.boundary_json,
                                    args.evidence_dir, args.output_dir,
                                    regions_json=args.regions_json)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
