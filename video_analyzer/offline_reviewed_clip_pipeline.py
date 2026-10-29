"""End-to-end offline gate -> FFmpeg clip export, with verified sidecar provenance.

Usage: python offline_reviewed_clip_pipeline.py VIDEO DRAFTS REVIEW HAND_ID CROP NEW_DIR

Requires the published offline_clip_review_gate.py and
 offline_reviewed_clip_export.py in the same directory. No poker analysis,
OCR validation, or automatic decision selection is performed.
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

from offline_clip_review_gate import prepare, load, sha, need
from offline_reviewed_clip_export import export


def inspect_clip(path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries',
            'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)],
            capture_output=True, text=True, check=True, timeout=30)
        obj = json.loads(result.stdout)
        streams = obj['streams']
        videos = [s for s in streams if s.get('codec_type') == 'video']
        duration = float(obj['format']['duration'])
        need(len(videos) == 1 and all(s.get('codec_type') != 'audio' for s in streams),
             'clip must contain one video stream and no audio')
        need(math.isfinite(duration) and duration > 0, 'invalid clip duration')
        return videos[0]['width'], videos[0]['height'], duration
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid exported clip metadata') from exc


def run(video, drafts, review, hand_id, crop, new_dir):
    video, drafts, review, crop, new_dir = map(Path, (video, drafts, review, crop, new_dir))
    need(new_dir.parent.is_dir() and not new_dir.parent.is_symlink()
         and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', new_dir.name)
         and not new_dir.exists() and not new_dir.is_symlink(), 'output must be a new directory')
    originals = {str(p.resolve()): sha(p) for p in (video, drafts, review, crop)}
    with tempfile.TemporaryDirectory(prefix='.plo_pipeline_', dir=new_dir.parent) as temporary:
        stage = Path(temporary)
        request, provenance = prepare(video, drafts, review, hand_id, crop, stage / 'gate')
        clip = stage / 'clip.mp4'
        meta = export(video, stage / 'gate' / 'request.json', clip)
        width, height, duration = inspect_clip(clip)
        expected_duration = request['end_seconds'] - request['start_seconds']
        need((width, height) == (request['crop']['width'], request['crop']['height']),
             'exported crop dimensions mismatch')
        need(abs(duration - expected_duration) <= 0.25, 'exported clip duration mismatch')
        sidecar = load(stage / 'clip.mp4.json')
        need(sidecar == meta and sidecar['source_video_sha256'] == request['source_video_sha256']
             and sidecar['source_request_sha256'] == sha(stage / 'gate' / 'request.json')
             and sidecar['clip_sha256'] == sha(clip)
             and sidecar['hand_id'] == hand_id and sidecar['table_id'] == request['table_id']
             and sidecar['audio_included'] is False
             and sidecar['video_evidence_verified'] is False
             and sidecar['automatic_clip_selection_authorized'] is False,
             'export provenance mismatch')
        need(provenance['source_video_matches_ocr_source_verified'] is False
             and provenance['ready_for_equity_or_ev'] is False,
             'invalid gate confidence claims')
        need(all(sha(p) == original for p in (video, drafts, review, crop)
                 for key, original in originals.items() if str(p.resolve()) == key),
             'source changed during pipeline')
        manifest = {
            'schema_version': 1,
            'analysis_status': 'offline_reviewed_clip_pipeline_evidence_only',
            'hand_id': hand_id, 'table_id': request['table_id'],
            'source_video_sha256': request['source_video_sha256'],
            'gate_request_sha256': sha(stage / 'gate' / 'request.json'),
            'gate_provenance_sha256': sha(stage / 'gate' / 'provenance.json'),
            'clip_sha256': sha(clip), 'clip_sidecar_sha256': sha(stage / 'clip.mp4.json'),
            'clip_duration_seconds': duration,
            'clip_dimensions': {'width': width, 'height': height},
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'source_video_matches_ocr_source_verified': False,
            'warning': 'Synthetic or manually reviewed clip; no validated poker hand or mathematical analysis.'
        }
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', 'utf-8')
        need(not new_dir.exists(), 'output appeared during processing')
        os.rename(stage, new_dir)
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'drafts', 'review', 'hand_id', 'crop', 'new_dir'):
        p.add_argument(name)
    a = p.parse_args(argv)
    result = run(a.video, a.drafts, a.review, a.hand_id, a.crop, a.new_dir)
    print(json.dumps({'analysis_status': result['analysis_status'], 'clip_sha256': result['clip_sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
