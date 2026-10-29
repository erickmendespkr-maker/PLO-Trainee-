"""Fail-closed offline binding: selected reviewed action -> replayed ROI -> MP4.

This verifies evidence identity, NOT OCR meaning, player identity, equity or EV.
Requires an existing source-replayed clip bundle and all original evidence.
Usage: python offline_selected_roi_clip_binding.py VIDEO REGIONS INGEST CHANGES
 REFINED TASKS OCR REVIEWED DRAFTS TIMELINE TRIAGE CLIP_BUNDLE HAND_ID INDEX NEW_JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from offline_action_evidence_viewer import build as build_viewer
from offline_action_review_triage import build as build_triage
from offline_ocr_source_replay_audit import audit as replay_audit

SHA = re.compile(r'[0-9a-f]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def load(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 8*1024*1024,
         'unsafe JSON evidence')
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def bind(video, regions, ingest, changes, refined, tasks, ocr, reviewed,
         drafts, timeline, triage, clip_bundle, hand_id, proposal_index, output):
    video, regions, ingest, changes, refined, tasks, ocr, reviewed, drafts, timeline, triage, clip_bundle, output = map(
        Path, (video, regions, ingest, changes, refined, tasks, ocr, reviewed,
               drafts, timeline, triage, clip_bundle, output))
    need(type(hand_id) is str and IDENT.fullmatch(hand_id) is not None
         and type(proposal_index) is int and 0 <= proposal_index <= 63,
         'invalid selected event identity')
    need(output.parent.is_dir() and not output.parent.is_symlink()
         and not output.exists() and not output.is_symlink()
         and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json', output.name),
         'output must be new JSON')
    dirs = (ingest, refined, ocr, clip_bundle)
    files = (video, regions, changes, tasks, reviewed, drafts, timeline, triage,
             ocr/'roi_ocr_proposals.json',
             clip_bundle/'source_replay_clip_attestation.json',
             clip_bundle/'reviewed_clip'/'triage_clip_link.json',
             clip_bundle/'reviewed_clip'/'manifest.json',
             clip_bundle/'reviewed_clip'/'clip.mp4')
    need(all(d.is_dir() and not d.is_symlink() for d in dirs)
         and all(f.is_file() and not f.is_symlink() for f in files), 'unsafe evidence paths')
    need(not any(output.resolve().is_relative_to(d.resolve()) for d in dirs)
         and output.resolve() not in {p.resolve() for p in files},
         'output overlaps evidence')
    fingerprints = {str(p): sha(p) for p in files}
    source_replay = replay_audit(video, regions, ingest, changes, refined, tasks, ocr)
    need(source_replay.get('source_video_to_frame_to_roi_reproduced') is True
         and source_replay.get('source_video_sha256') == sha(video)
         and source_replay.get('source_roi_ocr_report_sha256') == sha(ocr/'roi_ocr_proposals.json')
         and source_replay.get('ocr_semantics_verified') is False
         and source_replay.get('ready_for_equity_or_ev') is False,
         'media replay not verified')
    with tempfile.TemporaryDirectory(prefix='plo_selected_roi_binding_') as tmp:
        viewer_dir = Path(tmp)/'viewer'
        viewer = build_viewer(ocr, reviewed, drafts, timeline, viewer_dir)
        source_timeline = load(timeline)
        source_triage = load(triage)
        expected = build_triage(source_timeline)
        need(source_triage == dict(expected, source_timeline_sha256=sha(timeline)),
             'triage does not match timeline')
        matches = [c for c in expected['candidates'] if c['hand_id'] == hand_id
                   and c['proposal_index'] == proposal_index]
        need(len(matches) == 1 and matches[0]['clip_export_authorized'] is False,
             'candidate absent or ambiguous')
        selected = matches[0]
        hands = [h for h in viewer['hands'] if h['hand_id'] == hand_id]
        need(len(hands) == 1 and hands[0]['table_id'] == selected['table_id'],
             'viewer hand mismatch')
        events = [e for e in hands[0]['events'] if e['proposal_index'] == proposal_index]
        need(len(events) == 1 and events[0]['field'] == 'action'
             and events[0]['value'] == selected['action_ocr']
             and events[0]['timestamp_seconds'] == selected['timestamp_seconds'],
             'selected OCR event not bound to reviewed ROI')
        event = events[0]
        roi = ocr/f'roi_{proposal_index:03d}.png'
        need(roi.is_file() and not roi.is_symlink(), 'unsafe selected ROI')
        fingerprints[str(roi)] = sha(roi)
        need(event['roi_png_sha256'] == sha(roi)
             and sha(viewer_dir/event['roi_png']) == sha(roi), 'ROI identity mismatch')
        att = load(clip_bundle/'source_replay_clip_attestation.json')
        link = load(clip_bundle/'reviewed_clip'/'triage_clip_link.json')
        manifest = load(clip_bundle/'reviewed_clip'/'manifest.json')
        need(att.get('analysis_status') == 'offline_source_replayed_triage_clip_media_only'
             and att.get('source_video_to_frame_to_roi_reproduced') is True
             and att.get('source_video_matches_clip_source_verified') is True
             and att.get('ocr_text_linked_to_replayed_roi_verified') is False
             and att.get('ready_for_equity_or_ev') is False
             and att.get('source_video_sha256') == sha(video)
             and att.get('source_roi_ocr_report_sha256') == sha(ocr/'roi_ocr_proposals.json')
             and att.get('clip_sha256') == sha(clip_bundle/'reviewed_clip'/'clip.mp4')
             and att.get('clip_manifest_sha256') == sha(clip_bundle/'reviewed_clip'/'manifest.json')
             and att.get('triage_clip_link_sha256') == sha(clip_bundle/'reviewed_clip'/'triage_clip_link.json')
             and att.get('hand_id') == hand_id
             and att.get('proposal_index') == proposal_index,
             'source replay clip attestation mismatch')
        need(link.get('hand_id') == hand_id and link.get('proposal_index') == proposal_index
             and link.get('table_id') == selected['table_id']
             and link.get('timestamp_seconds') == selected['timestamp_seconds']
             and link.get('action_ocr') == selected['action_ocr']
             and link.get('source_timeline_sha256') == sha(timeline)
             and link.get('source_triage_sha256') == sha(triage)
             and link.get('source_hand_drafts_sha256') == sha(drafts)
             and link.get('source_video_sha256') == sha(video)
             and link.get('clip_sha256') == att['clip_sha256']
             and link.get('ready_for_equity_or_ev') is False
             and link.get('actor_identified') is False
             and link.get('clip_start_seconds') <= selected['timestamp_seconds'] < link.get('clip_end_seconds')
             and manifest.get('clip_sha256') == att['clip_sha256']
             and manifest.get('source_video_sha256') == sha(video)
             and manifest.get('ready_for_equity_or_ev') is False,
             'selected clip link or manifest mismatch')
        result = {
            'schema_version': 1,
            'analysis_status': 'offline_selected_action_roi_clip_identity_only',
            'hand_id': hand_id, 'table_id': selected['table_id'],
            'variant': selected['variant'], 'proposal_index': proposal_index,
            'timestamp_seconds': selected['timestamp_seconds'],
            'reviewed_action_text': event['value'], 'review_decision': event['review'],
            'roi_png_sha256': sha(roi), 'source_video_sha256': sha(video),
            'source_roi_ocr_report_sha256': sha(ocr/'roi_ocr_proposals.json'),
            'source_timeline_sha256': sha(timeline), 'source_triage_sha256': sha(triage),
            'source_clip_attestation_sha256': sha(clip_bundle/'source_replay_clip_attestation.json'),
            'clip_sha256': att['clip_sha256'],
            'selected_action_to_replayed_roi_verified': True,
            'selected_action_to_source_video_and_clip_verified': True,
            'ocr_semantics_verified': False, 'actor_identified': False,
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'warning': ('Hashes and review link the selected text to replayed ROI pixels '
                        'and exported clip, not to correct OCR meaning, player identity or strategy.')
        }
        need(all(sha(Path(p)) == h for p, h in fingerprints.items()),
             'source changed during binding')
        need(not output.exists(), 'output appeared during binding')
        with output.open('xb') as stream:
            stream.write((json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False)+'\n').encode('utf8'))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video','regions','ingest','changes','refined','tasks','ocr',
                 'reviewed','drafts','timeline','triage','clip_bundle','hand_id'):
        p.add_argument(name)
    p.add_argument('proposal_index',type=int)
    p.add_argument('new_output_json')
    args = p.parse_args(argv)
    result = bind(*vars(args).values())
    print(json.dumps({'analysis_status':result['analysis_status'],
                      'ready_for_equity_or_ev':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
