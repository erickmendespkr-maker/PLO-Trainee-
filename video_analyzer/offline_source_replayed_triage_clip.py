"""Offline reviewed triage MP4 gated by replay of source video, JPEG frames and OCR ROIs.

This validates media provenance, NOT OCR semantics, player identity, hand
reconstruction, equity, EV, or strategic correctness. All work stays offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from offline_ocr_source_replay_audit import audit as replay_audit
from offline_triage_reviewed_clip_pipeline import run as export_triage_clip

SAFE_DIR = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink()
         and 0 < path.stat().st_size <= 8 * 1024 * 1024, 'invalid evidence JSON')
    return json.loads(path.read_text('utf-8'))


def run(video, regions, ingest, changes, refined, tasks, ocr, drafts, review,
        crop, timeline, triage, hand_id, proposal_index, output_dir):
    inputs = [Path(p) for p in (video, regions, ingest, changes, refined,
                                tasks, ocr, drafts, review, crop, timeline, triage)]
    output_dir = Path(output_dir)
    need(SAFE_DIR.fullmatch(output_dir.name) is not None
         and output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
         and not output_dir.exists() and not output_dir.is_symlink(),
         'output must be a new safe directory')
    need(all(p.exists() and not p.is_symlink() for p in inputs),
         'missing or symlink input')
    need(all(not output_dir.resolve().is_relative_to(p.resolve()) for p in inputs),
         'output must not be inside evidence inputs')
    need(all(p.is_file() for p in inputs if p not in (inputs[2], inputs[4], inputs[6]))
         and all(p.is_dir() for p in (inputs[2], inputs[4], inputs[6])),
         'invalid input types')
    fixed = [inputs[i] for i in (0, 1, 3, 5, 7, 8, 9, 10, 11)] + [
        inputs[6] / 'roi_ocr_proposals.json']
    need(all(p.is_file() and not p.is_symlink() for p in fixed),
         'unsafe provenance input file')
    original_hashes = [sha(p) for p in fixed]
    replay_args = (inputs[0], inputs[1], inputs[2], inputs[3],
                   inputs[4], inputs[5], inputs[6])
    before = replay_audit(*replay_args)
    need(before.get('source_video_to_frame_to_roi_reproduced') is True
         and before.get('source_video_sha256') == original_hashes[0]
         and before.get('ocr_semantics_verified') is False
         and before.get('ready_for_equity_or_ev') is False
         and type(before.get('source_frames_replayed_exactly')) is int
         and before['source_frames_replayed_exactly'] > 0
         and type(before.get('roi_pngs_replayed_exactly')) is int
         and before['roi_pngs_replayed_exactly'] > 0,
         'media source replay did not establish limited provenance')

    with tempfile.TemporaryDirectory(prefix='.plo_replayed_clip_',
                                     dir=output_dir.parent) as tmp:
        stage = Path(tmp) / 'bundle'
        stage.mkdir()
        clip_dir = stage / 'reviewed_clip'
        link = export_triage_clip(inputs[0], inputs[7], inputs[8], inputs[9],
                                  inputs[10], inputs[11], hand_id,
                                  proposal_index, clip_dir)
        clip_manifest = read_json(clip_dir / 'manifest.json')
        clip = clip_dir / 'clip.mp4'
        need(clip.is_file() and not clip.is_symlink()
             and sha(clip) == link['clip_sha256'] == clip_manifest['clip_sha256']
             and link['source_video_sha256'] == clip_manifest['source_video_sha256']
             == before['source_video_sha256']
             and link['source_triage_sha256'] == original_hashes[8]
             and link['source_timeline_sha256'] == original_hashes[7]
             and link['source_hand_drafts_sha256'] == original_hashes[4]
             and link['source_video_matches_ocr_source_verified'] is False
             and link['ready_for_equity_or_ev'] is False
             and clip_manifest['ready_for_equity_or_ev'] is False,
             'clip media identity or conservative status mismatch')
        after = replay_audit(*replay_args)
        need(after == before, 'source replay changed during clip export')
        need([sha(p) for p in fixed] == original_hashes,
             'input file changed during clip export')
        need(not output_dir.exists(), 'output appeared during export')
        attestation = {
            'schema_version': 1,
            'analysis_status': 'offline_source_replayed_triage_clip_media_only',
            'source_video_sha256': before['source_video_sha256'],
            'source_roi_ocr_report_sha256': before['source_roi_ocr_report_sha256'],
            'source_frames_replayed_exactly': before['source_frames_replayed_exactly'],
            'roi_pngs_replayed_exactly': before['roi_pngs_replayed_exactly'],
            'source_video_to_frame_to_roi_reproduced': True,
            'source_video_matches_clip_source_verified': True,
            'same_ffmpeg_build_replay_required': True,
            'clip_sha256': link['clip_sha256'],
            'clip_manifest_sha256': sha(clip_dir / 'manifest.json'),
            'triage_clip_link_sha256': sha(clip_dir / 'triage_clip_link.json'),
            'hand_id': link['hand_id'],
            'proposal_index': link['proposal_index'],
            'clip_path': 'reviewed_clip/clip.mp4',
            'ocr_text_linked_to_replayed_roi_verified': False,
            'ocr_semantics_verified': False,
            'actor_identified': False,
            'hands_reconstructed': False,
            'ready_for_equity_or_ev': False,
            'strategic_correctness_verified': False,
            'warning': ('Source media and clip share a verified video hash. OCR ROI pixels '
                        'were reproduced independently, but the selected triage event is '
                        'NOT cryptographically linked to a specific replayed OCR ROI. '
                        'No OCR semantics, hand, player, equity, EV or decision is validated.')
        }
        (stage / 'source_replay_clip_attestation.json').write_text(
            json.dumps(attestation, indent=2, ensure_ascii=False, allow_nan=False)
            + '\n', encoding='utf-8')
        need(sha(clip) == attestation['clip_sha256']
             and sha(clip_dir / 'manifest.json') == attestation['clip_manifest_sha256']
             and not output_dir.exists(), 'stage changed before publication')
        os.rename(stage, output_dir)
    return attestation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'regions', 'ingest', 'changes', 'refined', 'tasks',
                 'ocr', 'drafts', 'review', 'crop', 'timeline', 'triage',
                 'hand_id'):
        parser.add_argument(name)
    parser.add_argument('proposal_index', type=int)
    parser.add_argument('new_output_dir')
    args = parser.parse_args(argv)
    result = run(*vars(args).values())
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'clip_sha256': result['clip_sha256'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
