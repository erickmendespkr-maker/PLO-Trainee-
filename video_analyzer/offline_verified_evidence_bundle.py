"""Build a read-only offline OCR viewer gated by actual source-video replay.

Usage:
 python offline_verified_evidence_bundle.py VIDEO REGIONS_JSON INGEST_DIR \
   CHANGES_JSON REFINED_DIR TASKS_JSON OCR_DIR REVIEWED_JSON DRAFTS_JSON \
   TIMELINE_JSON NEW_OUTPUT_DIR

Replays video->JPEG->OCR ROI via FFmpeg, builds the reviewed-event viewer,
replays a second time before publishing the new directory, and binds the
result to a SHA-256 manifest. Reproducibility is NOT OCR correctness, hand
reconstruction, equity, EV, authenticity or calibrated confidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from offline_ocr_source_replay_audit import audit
from offline_action_evidence_viewer import build as build_viewer


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def bundle(video, regions_json, ingest_dir, changes_json, refined_dir, tasks_json,
           ocr_dir, reviewed_json, drafts_json, timeline_json, output_dir):
    inputs = [Path(p) for p in (video, regions_json, ingest_dir, changes_json,
                               refined_dir, tasks_json, ocr_dir, reviewed_json,
                               drafts_json, timeline_json)]
    output_dir = Path(output_dir)
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name)
            and output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
            and not output_dir.exists() and not output_dir.is_symlink(),
            'output must be a new safe directory')
    output_resolved = output_dir.resolve()
    require(all(not output_resolved.is_relative_to(p.resolve()) for p in inputs),
            'output cannot be inside input evidence')
    require(all(p.exists() and not p.is_symlink() for p in inputs),
            'unsafe or missing input')
    audit_args = dict(zip(('video', 'regions_json', 'ingest_dir', 'changes_json',
                           'refined_dir', 'tasks_json', 'ocr_dir'), inputs[:7]))
    immutable_files = (inputs[0], inputs[1], inputs[3], inputs[5],
                       inputs[7], inputs[8], inputs[9], inputs[6] / 'roi_ocr_proposals.json')
    immutable_hashes = [sha(p) for p in immutable_files]
    initial = audit(**audit_args)
    require(initial.get('source_video_to_frame_to_roi_reproduced') is True
            and initial.get('ocr_semantics_verified') is False
            and initial.get('ready_for_equity_or_ev') is False
            and type(initial.get('roi_pngs_replayed_exactly')) is int
            and initial['roi_pngs_replayed_exactly'] > 0,
            'source replay did not establish a limited evidence chain')
    # Stage outside all inputs, then publish atomically only on full success.
    with tempfile.TemporaryDirectory(prefix='plo_verified_', dir=output_dir.parent) as temp:
        stage = Path(temp) / 'viewer'
        viewer = build_viewer(inputs[6], inputs[7], inputs[8], inputs[9], stage)
        require(viewer.get('source_roi_ocr_report_sha256') ==
                initial['source_roi_ocr_report_sha256'],
                'viewer OCR report does not match replayed source')
        require(viewer.get('ready_for_equity_or_ev') is False
                and viewer.get('hands_reconstructed') is False,
                'viewer falsely claims mathematical readiness')
        final_audit = audit(**audit_args)
        require(final_audit == initial, 'source replay changed during viewer generation')
        require([sha(p) for p in immutable_files] == immutable_hashes,
                'input report changed during verified viewer generation')
        report_path = stage / 'action_roi_report.json'
        html_path = stage / 'index.html'
        report_sha = sha(report_path)
        markup = html_path.read_text('utf-8')
        require(markup.count('<main>') == 1, 'unexpected viewer HTML layout')
        banner = ('<aside style="padding:12px;background:#183047;color:#fff">'
                  '<strong>Reprodução FFmpeg da origem conferida neste ambiente.</strong> '
                  'Isso não valida a interpretação OCR, as mãos ou decisões de pôquer. '
                  'Equity/EV indisponíveis.</aside>')
        html_path.write_text(markup.replace('<main>', banner + '<main>', 1), 'utf-8')
        attestation = {
            'schema_version': 1,
            'analysis_status': 'offline_source_replayed_reviewed_evidence_bundle_only',
            'source_video_sha256': initial['source_video_sha256'],
            'source_roi_ocr_report_sha256': initial['source_roi_ocr_report_sha256'],
            'source_frames_replayed_exactly': initial['source_frames_replayed_exactly'],
            'roi_pngs_replayed_exactly': initial['roi_pngs_replayed_exactly'],
            'viewer_report_sha256': report_sha,
            'viewer_html_sha256': sha(html_path),
            'same_ffmpeg_build_replay_required': True,
            'ocr_semantics_verified': False,
            'hands_reconstructed': False,
            'ready_for_equity_or_ev': False,
            'confidence': 'Exact media replay in this FFmpeg environment; no calibrated OCR correctness confidence',
            'warning': 'No poker decision, player, equity, EV or video authenticity has been verified.'
        }
        (stage / 'source_replay_attestation.json').write_text(
            json.dumps(attestation, indent=2, ensure_ascii=False, allow_nan=False) + '\n', 'utf-8')
        require(sha(report_path) == report_sha and
                sha(html_path) == attestation['viewer_html_sha256'] and
                not output_dir.exists(), 'bundle changed before publication')
        os.rename(stage, output_dir)
    return attestation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('video', 'regions_json', 'ingest_dir', 'changes_json', 'refined_dir',
                'tasks_json', 'ocr_dir', 'reviewed_json', 'drafts_json',
                'timeline_json', 'new_output_dir'):
        parser.add_argument(key)
    args = parser.parse_args(argv)
    print(json.dumps(bundle(*vars(args).values()), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
