"""Offline reviewed PLO5/PLO6 action -> MP4 evidence clip (no strategy claims).

Usage:
  python offline_triage_reviewed_clip_pipeline.py VIDEO DRAFTS_JSON BOUNDARY_REVIEW_JSON \
      CROP_JSON TIMELINE_JSON TRIAGE_JSON HAND_ID PROPOSAL_INDEX NEW_OUTPUT_DIR

Requires the local, previously published triage, gate, and clip pipeline modules.
A deterministic OCR triage candidate is linked to a *manually reviewed hand interval*;
no actor attribution, action legality, OCR accuracy, equity, EV or strategic
recommendation is inferred. The original video never leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import tempfile

from offline_action_review_triage import build as rebuild_triage
from offline_clip_review_gate import load, sha, need
from offline_reviewed_clip_pipeline import run as export_reviewed_clip

IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SAFE_DIR = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z')


def prepare_selection(drafts, timeline, queue, hand_id, proposal_index, timeline_hash):
    """Fail closed on forged triage and mismatched hand/source identity."""
    need(type(hand_id) is str and IDENT.fullmatch(hand_id) is not None
         and type(proposal_index) is int and proposal_index >= 0, 'invalid candidate identity')
    expected = rebuild_triage(timeline)
    need(queue == dict(expected, source_timeline_sha256=timeline_hash),
         'triage must exactly match the source timeline')
    need(type(drafts) is dict and drafts.get('analysis_status') == 'offline_reviewed_hand_drafts_only'
         and drafts.get('hands_reconstructed') is False
         and drafts.get('ready_for_equity_or_ev') is False
         and type(drafts.get('hands')) is list, 'invalid drafts')
    need(timeline.get('source_reviewed_report_sha256') == drafts.get('source_reviewed_report_sha256')
         and timeline.get('source_boundaries_sha256') == drafts.get('source_boundaries_sha256'),
         'timeline and drafts provenance mismatch')
    candidates = [c for c in expected['candidates'] if c['hand_id'] == hand_id
                  and c['proposal_index'] == proposal_index]
    need(len(candidates) == 1, 'candidate not found or ambiguous')
    candidate = candidates[0]
    hands = [h for h in drafts['hands'] if type(h) is dict and h.get('hand_id') == hand_id]
    source_hands = [h for h in timeline['hands'] if h['hand_id'] == hand_id]
    need(len(hands) == len(source_hands) == 1, 'missing hand')
    draft, source = hands[0], source_hands[0]
    need(all(draft.get(k) == source.get(k) for k in
             ('hand_id', 'table_id', 'variant', 'start_seconds', 'end_seconds'))
         and draft['table_id'] == candidate['table_id']
         and draft['variant'] == candidate['variant']
         and candidate['actor_identified'] is False
         and candidate['ready_for_equity_or_ev'] is False
         and candidate['clip_export_authorized'] is False,
         'candidate is not linked to the original unverified hand')
    return candidate


def run(video, drafts_path, review_path, crop_path, timeline_path, queue_path,
        hand_id, proposal_index, output_dir):
    paths = [Path(p) for p in (video, drafts_path, review_path, crop_path,
                              timeline_path, queue_path)]
    output_dir = Path(output_dir)
    need(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
         and SAFE_DIR.fullmatch(output_dir.name) is not None
         and not output_dir.exists() and not output_dir.is_symlink(),
         'output must be a new safe directory')
    need(len({p.resolve() for p in paths}) == len(paths)
         and output_dir.resolve() not in {p.resolve() for p in paths},
         'input paths must be distinct')
    for p in (paths[4], paths[5]):
        need(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 8 * 1024 * 1024,
             'unsafe timeline/triage file')
    source_hashes = [sha(p) for p in paths]
    drafts, timeline, queue = (load(paths[1]), load(paths[4]), load(paths[5]))
    candidate = prepare_selection(drafts, timeline, queue, hand_id,
                                  proposal_index, source_hashes[4])
    with tempfile.TemporaryDirectory(prefix='.plo_triage_clip_', dir=output_dir.parent) as temp:
        stage = Path(temp) / 'bundle'
        manifest = export_reviewed_clip(paths[0], paths[1], paths[2], hand_id,
                                        paths[3], stage)
        request = load(stage / 'gate' / 'request.json')
        need(request['hand_id'] == hand_id
             and request['table_id'] == candidate['table_id']
             and request['start_seconds'] <= candidate['timestamp_seconds'] < request['end_seconds']
             and manifest['source_video_sha256'] == source_hashes[0]
             and manifest['clip_sha256'] == sha(stage / 'clip.mp4')
             and manifest['ready_for_equity_or_ev'] is False
             and manifest['source_video_matches_ocr_source_verified'] is False,
             'reviewed clip does not cover selected action')
        link = {
            'schema_version': 1,
            'analysis_status': 'offline_triage_link_to_manually_reviewed_clip_only',
            'hand_id': hand_id,
            'table_id': candidate['table_id'],
            'variant': candidate['variant'],
            'proposal_index': proposal_index,
            'action_ocr': candidate['action_ocr'],
            'timestamp_seconds': candidate['timestamp_seconds'],
            'review_priority_points': candidate['review_priority_points'],
            'source_timeline_sha256': source_hashes[4],
            'source_triage_sha256': source_hashes[5],
            'source_hand_drafts_sha256': source_hashes[1],
            'source_boundary_review_sha256': source_hashes[2],
            'source_video_sha256': source_hashes[0],
            'gate_request_sha256': sha(stage / 'gate' / 'request.json'),
            'clip_sha256': manifest['clip_sha256'],
            'clip_start_seconds': request['start_seconds'],
            'clip_end_seconds': request['end_seconds'],
            'clip_path': 'clip.mp4',
            'actor_identified': False,
            'action_legality_verified': False,
            'hands_reconstructed': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'source_video_matches_ocr_source_verified': False,
            'warning': ('Human-approved hand boundaries, not an approved poker decision. '
                        'OCR action and triage priority are uncalibrated evidence; '
                        'equity, EV, ranges and strategic correctness are unknown.')
        }
        (stage / 'triage_clip_link.json').write_text(
            json.dumps(link, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')
        need(all(sha(p) == original for p, original in zip(paths, source_hashes)),
             'source changed during export')
        need(not output_dir.exists(), 'output appeared during export')
        os.rename(stage, output_dir)
    return link


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'drafts', 'boundary_review', 'crop', 'timeline',
                 'triage', 'hand_id'):
        parser.add_argument(name)
    parser.add_argument('proposal_index', type=int)
    parser.add_argument('new_output_dir')
    args = parser.parse_args(argv)
    link = run(args.video, args.drafts, args.boundary_review, args.crop,
               args.timeline, args.triage, args.hand_id, args.proposal_index,
               args.new_output_dir)
    print(json.dumps({'hand_id': link['hand_id'], 'proposal_index': link['proposal_index'],
                      'clip_sha256': link['clip_sha256'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
