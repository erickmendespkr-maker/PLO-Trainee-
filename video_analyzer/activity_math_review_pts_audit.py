"""Audit decoded PTS of previously exported *navigation* PNGs.

Re-decodes the original video at the same requested seek, using FFmpeg's
showinfo filter and copyts, and only associates decoded PTS when the re-decoded
PNG is byte-identical to the previously hash-verified PNG. This is NOT an
independent recognition of cards, hands, actions or correct strategy.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from activity_math_review_frames import build_math_review_frame_plan

STATUS = 'decoded_pts_audited_navigation_only_no_math_or_clip_authority'
PTS_LINE = re.compile(r'\bn:\s*0\s+pts:\s*(-?\d+)\s+pts_time:\s*([-+\d.eE]+)\b')
TIMEBASE = re.compile(r'config in time_base:\s*(\d+/\d+)')
HEX = re.compile(r'[0-9a-f]{64}\Z')


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _file(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('Require regular non-symlink source file')
    return p


def _parse_decoded_pts(stderr):
    lines = [line for line in stderr.splitlines() if 'showinfo' in line and PTS_LINE.search(line)]
    if len(lines) != 1:
        raise ValueError('Expected exactly one decoded showinfo frame')
    match = PTS_LINE.search(lines[0])
    pts_ticks, pts_seconds = int(match.group(1)), float(match.group(2))
    if not math.isfinite(pts_seconds):
        raise ValueError('Non-finite decoded PTS')
    bases = TIMEBASE.findall(stderr)
    if len(set(bases)) != 1:
        raise ValueError('Missing or ambiguous FFmpeg filtergraph time base')
    num, den = map(int, bases[0].split('/'))
    if num <= 0 or den <= 0 or abs(pts_ticks * num / den - pts_seconds) > 0.00001:
        raise ValueError('Decoded PTS and time base disagree')
    return pts_ticks, pts_seconds, bases[0]


def audit_math_review_pts(video_path, frames_dir, handoff_json, triage_json,
                          packet_json, timeline_json, output_dir):
    """Publish a new JSON audit, never modify upstream stills or manifests."""
    video = _file(video_path)
    sources = [_file(x) for x in (handoff_json, triage_json, packet_json, timeline_json)]
    frames = Path(frames_dir)
    output = Path(output_dir)
    if (frames.is_symlink() or not frames.is_dir() or output.exists() or output.is_symlink()
            or output.resolve().is_relative_to(frames.resolve())):
        raise ValueError('Require an existing real frames directory and new output outside it')
    manifest_path = _file(frames / 'math_review_frames.json')
    input_paths = [video, *sources, manifest_path]
    input_hashes = [_sha(p) for p in input_paths]
    handoff, triage, packet, timeline = [json.loads(p.read_text(encoding='utf-8')) for p in sources]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('frames'), list):
        raise ValueError('Invalid frame manifest')
    count = manifest.get('counts', {}).get('frames_planned')
    if type(count) is not int or not 0 <= count <= 100:
        raise ValueError('Invalid frame count')
    baseline = build_math_review_frame_plan(video, handoff, triage, packet, timeline,
                                            max_frames=max(1, count))
    stripped = dict(manifest)
    stripped['frames'] = []
    verified = []
    for item in manifest['frames']:
        if not isinstance(item, dict) or set(item) != set(baseline['frames'][0] if baseline['frames'] else {}):
            raise ValueError('Unexpected frame fields')
        filename = item['filename']
        if not isinstance(filename, str) or not re.fullmatch(r'frame_[0-9]{4}\.png', filename):
            raise ValueError('Unsafe frame filename')
        sha = item['sha256']
        if not isinstance(sha, str) or not HEX.fullmatch(sha):
            raise ValueError('Missing frame SHA-256')
        still = _file(frames / filename)
        if _sha(still) != sha:
            raise ValueError('Source still SHA-256 mismatch')
        verified.append((item, still))
        stripped['frames'].append({**item, 'sha256': None})
    if stripped != baseline:
        raise ValueError('Frame manifest differs from independently recomputed plan')
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='.plo_pts_audit_', dir=output.parent) as tmp:
        stage = Path(tmp)
        for item, still in verified:
            duplicate = stage / item['filename']
            run = subprocess.run(
                ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info',
                 '-copyts', '-ss', str(item['requested_seek_pts_seconds']),
                 '-i', str(video), '-vf', 'showinfo', '-frames:v', '1',
                 '-update', '1', '-y', str(duplicate)],
                check=True, capture_output=True, text=True, timeout=60)
            ticks, seconds, timebase = _parse_decoded_pts(run.stderr)
            if not duplicate.is_file() or duplicate.stat().st_size < 100:
                raise ValueError('Re-decoding produced no PNG')
            matched = _sha(duplicate) == item['sha256']
            rows.append({
                'filename': item['filename'],
                'requested_seek_pts_seconds': item['requested_seek_pts_seconds'],
                'source_png_sha256': item['sha256'],
                'redecoded_png_sha256': _sha(duplicate),
                'png_bytes_match': matched,
                'decoded_frame_pts_seconds': seconds if matched else None,
                'decoded_frame_pts_ticks': ticks if matched else None,
                'decoded_frame_time_base': timebase if matched else None,
                'requested_to_decoded_delta_seconds': (seconds - item['requested_seek_pts_seconds'])
                    if matched else None,
                'timestamp_semantics': 'ffmpeg_filtergraph_decoded_pts_not_wall_clock'
                    if matched else 'unverified_due_to_frame_mismatch',
            })
        # Re-check every upstream byte after FFmpeg, including all PNGs.
        if any(_sha(path) != digest for path, digest in zip(input_paths, input_hashes)):
            raise ValueError('Source inputs changed during audit')
        if any(_sha(still) != item['sha256'] for item, still in verified):
            raise ValueError('Source still changed during audit')
        report = {
            'schema_version': 1, 'analysis_status': STATUS,
            'recording_sha256': input_hashes[0],
            'source_full_frame_manifest_sha256': input_hashes[-1],
            'frames': rows,
            'counts': {'frames_checked': len(rows),
                       'byte_identical_decodes': sum(x['png_bytes_match'] for x in rows),
                       'unverified_pts': sum(not x['png_bytes_match'] for x in rows)},
            'source_visual_content_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': ('Decoded PTS applies only to byte-identical re-decoded PNGs. '
                        'This is FFmpeg filtergraph time, not wall-clock capture time. '
                        'No OCR, card/action, hand-boundary, equity, EV or clip approval.'),
        }
        (stage / 'math_review_pts_audit.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        os.replace(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'frames_dir', 'handoff_json', 'triage_json', 'packet_json',
                 'timeline_json', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    report = audit_math_review_pts(args.video, args.frames_dir, args.handoff_json,
                                   args.triage_json, args.packet_json,
                                   args.timeline_json, args.output_dir)
    print(json.dumps(report['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
