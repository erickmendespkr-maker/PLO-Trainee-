"""Gate offline PLO5/PLO6 equity on a complete, hash-linked human frame acknowledgement.

Usage:
  python offline_acknowledged_equity_clip_report.py BINDING_JSON CLIP_MP4 \
    MANUAL_REVIEW_JSON SNAPSHOT_DIR CONFIRMATION_JSON NEW_REPORT_JSON

All card labels and acknowledgements remain HUMAN ASSERTIONS, not machine-verified
visibility or OCR. The earlier source-video replay audit is NOT rerun here.
Monte Carlo confidence intervals cover sampling error, not range/model uncertainty.
No live-poker interaction, action grading, or opponent inference is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from offline_audited_card_gallery import load as load_gallery, verify as verify_gallery
from offline_plo_equity_monte_carlo import require
from offline_reviewed_equity_clip_report import build as build_equity, digest, safe_file


def build(binding_path, clip_path, manual_path, snapshot_dir, confirmation_path):
    binding = safe_file(binding_path, max_bytes=2_000_000)
    clip = safe_file(clip_path)
    manual = safe_file(manual_path, max_bytes=2_000_000)
    confirmation = safe_file(confirmation_path, max_bytes=2_000_000)
    sources = (binding, clip, manual, confirmation)
    require(len({p.resolve() for p in sources}) == len(sources), 'input files must differ')
    root = Path(snapshot_dir)
    require(root.is_dir() and not root.is_symlink(), 'invalid snapshot directory')
    require(root.resolve() not in {p.resolve() for p in sources}, 'invalid source layout')
    manifest, review, frames, manifest_sha, review_sha = load_gallery(root, manual)
    require(manifest['source_binding_sha256'] == digest(binding) and
            manifest['source_clip_sha256'] == digest(clip),
            'snapshot does not match selected clip and binding')
    before = {str(p.resolve()): digest(p) for p in sources}
    acknowledged = verify_gallery(root, manual, confirmation)
    require(acknowledged['human_confirmation_asserted'] is True and
            acknowledged['acknowledged_cards'] == len(review['hero_cards'] + review['board_cards']) and
            acknowledged['source_manifest_sha256'] == manifest_sha and
            acknowledged['source_manual_review_sha256'] == review_sha and
            acknowledged['source_confirmation_sha256'] == before[str(confirmation.resolve())],
            'incomplete or unrelated human acknowledgement')
    report = build_equity(binding, clip, manual)
    require(report['source_binding_sha256'] == before[str(binding.resolve())] and
            report['source_clip_sha256'] == before[str(clip.resolve())] and
            report['source_manual_review_sha256'] == before[str(manual.resolve())],
            'equity report source mismatch')
    require(report['hand_id'] == manifest['hand_id'] and
            report['table_id'] == manifest['table_id'] and
            report['variant'] == manifest['variant'] and
            report['proposal_index'] == manifest['proposal_index'] and
            report['card_frame_evidence_count'] == acknowledged['acknowledged_cards'],
            'equity report does not cover acknowledged cards')
    # Re-validate the frame bytes as well as the input JSON after Monte Carlo.
    after_manifest, _, after_frames, after_msha, after_rsha = load_gallery(root, manual)
    require(after_msha == manifest_sha and after_rsha == review_sha and
            after_frames == frames and after_manifest == manifest and
            all(digest(p) == before[str(p.resolve())] for p in sources), 'evidence changed during calculation')
    # The output deliberately retains all the previous caveats, and does not
    # upgrade human assertions into machine-verified card visibility.
    return {
        **report,
        'analysis_status': 'offline_conditional_equity_after_human_frame_acknowledgement',
        'source_snapshot_manifest_sha256': manifest_sha,
        'source_gallery_confirmation_sha256': before[str(confirmation.resolve())],
        'human_snapshot_acknowledgement_validated': True,
        'human_acknowledged_cards': acknowledged['acknowledged_cards'],
        'card_visibility_machine_verified': False,
        'decoded_frame_pts_verified': False,
        'reviewed_cards_are_human_assertions': True,
        'source_video_replay_audit_rerun': False,
        'warning': (
            'Human acknowledged each declared card/frame association; this is not '
            'automatic card recognition, proof of visibility, OCR accuracy, hero identity, '
            'or an action grade. Earlier video replay was not rerun. Equity is conditional '
            'on manually entered cards and opponent ranges. The 95% interval only '
            'quantifies Monte Carlo sampling error, not range/model uncertainty.'
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding_json', 'clip_mp4', 'manual_review_json', 'snapshot_dir',
                 'confirmation_json', 'new_report_json'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    output = Path(args.new_report_json)
    require(output.suffix == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists() and
            not output.is_symlink(), 'output must be a new JSON file')
    sources = [args.binding_json, args.clip_mp4, args.manual_review_json,
               args.confirmation_json]
    require(output.resolve() not in {Path(p).resolve() for p in sources} and
            output.resolve() != Path(args.snapshot_dir, 'manifest.json').resolve(),
            'cannot overwrite evidence')
    report = build(args.binding_json, args.clip_mp4, args.manual_review_json,
                   args.snapshot_dir, args.confirmation_json)
    with output.open('x', encoding='utf-8') as file:
        json.dump(report, file, indent=2, ensure_ascii=False, allow_nan=False)
        file.write('\n')
    print(json.dumps({'analysis_status': report['analysis_status'],
                      'equity': report['equity_result']['equity'],
                      'human_acknowledged_cards': report['human_acknowledged_cards'],
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
