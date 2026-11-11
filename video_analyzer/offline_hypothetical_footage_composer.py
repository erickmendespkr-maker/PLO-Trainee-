"""Append an illustrative EV card to an independently selected OFFLINE MP4 excerpt.

Usage: python offline_hypothetical_footage_composer.py EXCERPT.mp4 MATH.json ACK.json NEW_RESULT.mp4

EXCERPT.mp4.json is a sidecar from offline_reviewed_clip_export or a deliberately
unverified sample manifest. This is NOT verified poker decision analysis. It
never says a hypothetical range matches the action seen in the footage.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from offline_hypothetical_ev_video import need, render, sha, validate

HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
MAX_BYTES = 8 * 1024**3
MAX_JSON = 64 * 1024


def strict_json(path):
    p = Path(path)
    need(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
         'missing or oversized JSON source')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            need(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def decimal(v, lo, hi):
    return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi


def check_clip_sidecar(meta, clip_sha):
    need(type(meta) is dict and meta.get('schema_version') == 1 and
         type(meta['schema_version']) is int and
         meta.get('analysis_status') in (
             'manually_selected_offline_clip', 'unverified_excerpt_for_illustration_only') and
         meta.get('clip_sha256') == clip_sha and
         meta.get('video_evidence_verified') is False and
         meta.get('automatic_clip_selection_authorized') is False and
         meta.get('audio_included') is False,
         'clip sidecar must remain unverified and hash-bound')
    need(type(meta.get('table_id')) is int and 1 <= meta['table_id'] <= 4 and
         type(meta.get('hand_id')) is str and IDENT.fullmatch(meta['hand_id']) and
         decimal(meta.get('start_seconds'), 0, 5400) and
         decimal(meta.get('end_seconds'), 0, 5400) and
         .1 <= meta['end_seconds'] - meta['start_seconds'] <= 180,
         'invalid source clip time/table')
    need(type(meta.get('source_video_sha256')) is str and
         HEX.fullmatch(meta['source_video_sha256']), 'source video origin SHA missing')
    # The upstream exporter is a source of metadata claims, not an oracle about
    # the actual poker facts or a guarantee of human annotation quality.
    if meta['analysis_status'] == 'manually_selected_offline_clip':
        need(type(meta.get('source_request_sha256')) is str and
             HEX.fullmatch(meta['source_request_sha256']) and
             type(meta.get('explanation')) is str,
             'invalid reviewed clip exporter provenance')
    else:
        need(meta.get('manual_sample_only') is True,
             'unverified excerpt must explicitly disclose manual sample status')


def check_ack(ack, clip_sha, math_sha, math):
    need(type(ack) is dict and set(ack) == {
        'schema_version', 'status', 'source_clip_sha256', 'source_math_sha256',
        'scenario_id', 'reviewer_acknowledged_not_observed_analysis', 'reviewer_note'},
        'invalid acknowledgement schema')
    need(type(ack['schema_version']) is int and ack['schema_version'] == 1 and
         ack['status'] == 'illustrative_footage_plus_hypothetical_math_only' and
         ack['source_clip_sha256'] == clip_sha and
         ack['source_math_sha256'] == math_sha and
         ack['scenario_id'] == math['scenario_id'] and
         ack['reviewer_acknowledged_not_observed_analysis'] is True and
         type(ack['reviewer_note']) is str and
         10 <= len(ack['reviewer_note'].strip()) <= 200 and
         all(c in '\n\t' or 32 <= ord(c) < 127 for c in ack['reviewer_note']),
         'missing explicit illustrative-only acknowledgement')


def run_ffmpeg(args, timeout):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg/FFprobe failed or timed out') from exc
    need(result.returncode == 0, 'FFmpeg/FFprobe failed: ' +
         result.stderr[-500:].decode('utf-8', 'replace'))
    return result


def probe_video(clip):
    raw = run_ffmpeg(['ffprobe', '-v', 'error', '-show_entries',
                      'format=duration:stream=codec_type,width,height', '-of', 'json',
                      str(clip)], 30).stdout
    need(len(raw) <= 100_000, 'oversized probe output')
    details = json.loads(raw)
    streams = details.get('streams')
    need(type(streams) is list and len([s for s in streams if s.get('codec_type')=='video']) == 1 and
         not any(s.get('codec_type') == 'audio' for s in streams), 'expected video only')
    video = next(s for s in streams if s.get('codec_type') == 'video')
    duration = float(details.get('format', {}).get('duration', 'nan'))
    need(type(video.get('width')) is int and type(video.get('height')) is int and
         2 <= video['width'] <= 8192 and 2 <= video['height'] <= 8192 and
         decimal(duration, .1, 190), 'invalid output/input geometry or duration')
    return {'duration_seconds': duration, 'width': video['width'],
            'height': video['height']}


def compose(clip, math_report, acknowledgment, output):
    clip, math_report, acknowledgment, output = map(
        Path, (clip, math_report, acknowledgment, output))
    clip_sidecar = Path(str(clip) + '.json')
    out_sidecar = Path(str(output) + '.json')
    sources = (clip, clip_sidecar, math_report, acknowledgment)
    need(clip.is_file() and not clip.is_symlink() and
         clip.suffix.lower() == '.mp4' and 0 < clip.stat().st_size <= MAX_BYTES,
         'unsafe source excerpt')
    need(output.suffix.lower() == '.mp4' and output.parent.is_dir() and
         not output.parent.is_symlink() and not output.exists() and
         not output.is_symlink() and not out_sidecar.exists() and
         not out_sidecar.is_symlink() and
         len({p.resolve() for p in sources + (output, out_sidecar)}) == 6,
         'new distinct output files required')
    hashes = {str(p.resolve()): sha(p) for p in sources}
    clip_sha = hashes[str(clip.resolve())]
    math_sha = hashes[str(math_report.resolve())]
    meta, math, ack = [strict_json(p) for p in (clip_sidecar, math_report, acknowledgment)]
    check_clip_sidecar(meta, clip_sha)
    validate(math)
    check_ack(ack, clip_sha, math_sha, math)
    excerpt_info = probe_video(clip)
    need(abs(excerpt_info['duration_seconds'] -
             (meta['end_seconds'] - meta['start_seconds'])) <= .8,
         'excerpt length inconsistent with source timing claims')
    with tempfile.TemporaryDirectory(prefix='.plo_illustrative_clip_', dir=output.parent) as d:
        root = Path(d)
        card = root / 'card.mp4'
        card_meta = render(math_report, card)
        card_info = probe_video(card)
        combined = root / 'combined.mp4'
        # Labels on the *footage itself* prevent an isolated cut from implying
        # that the illustrative math is an observed poker analysis.
        vf = ('[0:v]scale=1280:720:force_original_aspect_ratio=decrease,'
              'pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=15,'
              "drawtext=text='VIDEO GRAVADO - EXEMPLO SEM VALIDACAO ESTRATEGICA':"
              'fontcolor=yellow:fontsize=24:box=1:boxcolor=black@0.8:'
              'boxborderw=8:x=(w-text_w)/2:y=24,setpts=PTS-STARTPTS[v0];'
              '[1:v]fps=15,setsar=1,setpts=PTS-STARTPTS[v1];'
              '[v0][v1]concat=n=2:v=1:a=0[v]')
        run_ffmpeg(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(clip), '-i', str(card), '-filter_complex', vf,
                    '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(combined)], 180)
        result_info = probe_video(combined)
        need(result_info['width'] == 1280 and result_info['height'] == 720 and
             abs(result_info['duration_seconds'] - excerpt_info['duration_seconds'] -
                 card_info['duration_seconds']) <= .25,
             'unexpected combined video output')
        need(all(sha(p) == h for p,h in ((Path(k),v) for k,v in hashes.items())),
             'input changed during combined export')
        result = {
            'schema_version': 1,
            'analysis_status': 'illustrative_recorded_excerpt_plus_hypothetical_ev_not_poker_verdict',
            'source_clip_sha256': clip_sha,
            'source_clip_sidecar_sha256': hashes[str(clip_sidecar.resolve())],
            'source_video_sha256_claim_not_reverified': meta['source_video_sha256'],
            'source_math_sha256': math_sha,
            'source_acknowledgement_sha256': hashes[str(acknowledgment.resolve())],
            'intermediate_hypothetical_card_sha256': card_meta['mp4_sha256'],
            'combined_mp4_sha256': sha(combined),
            'source_clip_table_id_claim': meta['table_id'],
            'source_clip_hand_id_claim': meta['hand_id'],
            'source_clip_start_seconds_claim': meta['start_seconds'],
            'source_clip_end_seconds_claim': meta['end_seconds'],
            'hypothetical_scenario_id': math['scenario_id'],
            'hypothetical_range_sensitive': math['range_sensitive'],
            'video_excerpt': excerpt_info, 'math_card': card_info,
            'combined_video': result_info, 'audio_included': False,
            'human_acknowledged_illustrative_only': True,
            'cards_actions_ranges_verified_from_video': False,
            'source_hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
            'warning': ('This joins recorded footage to an UNRELATED HYPOTHETICAL range/EV example. '
                        'Neither card nor video establishes real hand equity, EV, or GTO error. '
                        'Source clip timing and attribution are claims from its sidecar, '
                        'not independent reconstruction of the source recording.')
        }
        stage = root / 'combined.mp4.json'
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n', 'utf-8')
        os.link(combined, output)
        try:
            os.link(stage, out_sidecar)
        except OSError:
            output.unlink(missing_ok=True)
            raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_excerpt_mp4')
    parser.add_argument('hypothetical_ev_json')
    parser.add_argument('acknowledgment_json')
    parser.add_argument('new_combined_mp4')
    a = parser.parse_args()
    r = compose(a.source_excerpt_mp4, a.hypothetical_ev_json,
                a.acknowledgment_json, a.new_combined_mp4)
    print(json.dumps({'status':r['analysis_status'],
                      'mp4_sha256':r['combined_mp4_sha256']}))


if __name__ == '__main__':
    main()
