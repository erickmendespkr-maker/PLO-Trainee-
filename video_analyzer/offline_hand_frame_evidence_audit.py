"""Offline provenance audit of hand/street reviewer claims against saved frame bytes.

Usage: python offline_hand_frame_evidence_audit.py OCR_LEDGER.json RECONSTRUCTION.json REVIEW_LEDGER.json FRAMES_DIR NEW_AUDIT.json [--video VIDEO.mp4]

This verifies file hashes and claim-to-observation links, NOT what the picture depicts.
No math-ready output, equity, EV, live capture, or network activity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image
import offline_hand_street_review as review
import offline_ocr_hand_reconstruction as reconstruct

MAX_FRAMES = 12
MAX_FRAME_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_manifest(directory, ledger):
    require(directory.is_dir() and not directory.is_symlink(), 'invalid frame directory')
    manifest_path = directory / 'manifest.json'
    manifest = review.read(manifest_path)
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            manifest.get('status') == 'offline_multiframe_roi_geometry_unverified' and
            manifest.get('ocr_confirmed') is False and
            manifest.get('eligible_for_equity') == 0 and
            type(manifest.get('eligible_for_equity')) is int and
            manifest.get('manual_review_required') is True and
            manifest.get('source_video_sha256') == ledger['source_video_sha256_claim'] and
            manifest.get('source_plan_sha256') == ledger['source_plan_sha256'] and
            review.digest(manifest_path) == ledger['source_frame_manifest_sha256'] and
            type(manifest.get('frames')) is list and
            1 <= len(manifest['frames']) <= MAX_FRAMES,
            'frame manifest provenance mismatch')
    frames = {}
    used_names = set()
    total = 0
    for row in manifest['frames']:
        require(type(row) is dict and
                {'hand_id', 'table_id', 'pts_seconds', 'frame', 'frame_sha256'} <= set(row) and
                type(row['hand_id']) is str and type(row['table_id']) is str and
                review.ID.fullmatch(row['hand_id']) and review.ID.fullmatch(row['table_id']) and
                type(row['pts_seconds']) in (int, float) and
                0 <= row['pts_seconds'] <= 14400 and
                type(row['frame']) is str and
                __import__('re').fullmatch(r'frame_[0-9]{3}\.png', row['frame']) and
                type(row['frame_sha256']) is str and review.SHA.fullmatch(row['frame_sha256']) and
                row['frame'] not in used_names,
                'invalid or duplicate frame entry')
        used_names.add(row['frame'])
        file = directory / row['frame']
        require(file.is_file() and not file.is_symlink() and
                0 < file.stat().st_size <= MAX_FRAME_BYTES and
                review.digest(file) == row['frame_sha256'],
                'missing or altered frame bytes')
        total += file.stat().st_size
        require(total <= MAX_TOTAL_BYTES, 'frame bytes exceed limit')
        with Image.open(file) as image:
            require(image.format == 'PNG' and 64 <= image.width <= 8192 and
                    64 <= image.height <= 8192, 'invalid PNG frame')
            image.verify()
        key = (row['hand_id'], row['table_id'], row['frame_sha256'])
        require(key not in frames, 'ambiguous frame hash for hand/table')
        frames[key] = row['pts_seconds']
    return frames


def build(ocr_path, reconstruction_path, reviewed_path, frame_directory, video_path=None):
    paths = [Path(p) for p in (ocr_path, reconstruction_path, reviewed_path)]
    hashes = [review.digest(p) for p in paths]
    ocr, reconstruction, reviewed = [review.read(p) for p in paths]
    # Rebuild the reconstruction, rather than trusting a user-edited report.
    expected = reconstruct.build(ocr, hashes[0])
    require(reconstruction == expected, 'reconstruction differs from OCR source')
    require(type(reviewed) is dict and
            reviewed.get('status') == 'offline_hand_street_review_import_unverified_not_math_ready' and
            reviewed.get('schema_version') == 1 and
            reviewed.get('source_reconstruction_sha256') == hashes[1] and
            reviewed.get('source_ledger_sha256') == hashes[0] and
            reviewed.get('source_video_sha256_claim') == ocr['source_video_sha256_claim'] and
            reviewed.get('eligible_for_equity') == 0 and
            type(reviewed.get('eligible_for_equity')) is int and
            reviewed.get('equity_or_ev_calculated') is False and
            reviewed.get('reviewer_claims_not_authenticated') is True and
            reviewed.get('original_video_cards_not_independently_verified') is True and
            type(reviewed.get('hands')) is list and
            len(reviewed['hands']) == len(reconstruction['hands']),
            'review ledger provenance mismatch')
    frames = validate_manifest(Path(frame_directory), ocr)
    verified_video_hash = False
    if video_path is not None:
        video = Path(video_path)
        require(video.is_file() and not video.is_symlink() and
                video.suffix.lower() in ('.mp4', '.webm') and
                review.digest(video) == ocr['source_video_sha256_claim'],
                'source video SHA-256 mismatch')
        verified_video_hash = True
    rows = {}
    for observation in ocr['decisions']:
        key = (observation['hand_id'], observation['table_id'],
               observation['field'], observation['slot'])
        rows.setdefault(key, []).append(observation)
    results = []
    for hand, source in zip(reviewed['hands'], reconstruction['hands']):
        require(type(hand) is dict and hand.get('hand_id') == source['hand_id'] and
                hand.get('table_id') == source['table_id'] and
                hand.get('math_ready') is False and hand.get('eligible_for_equity') is False and
                type(hand.get('fields')) is list and len(hand['fields']) <= 20,
                'review hand identity mismatch')
        claims = []
        seen = set()
        for field in hand['fields']:
            require(type(field) is dict and field.get('field') in
                    ('hero_card', 'board_card', 'action', 'pot', 'stack', 'variant') and
                    type(field.get('review_status')) is str and
                    field['review_status'] in ('unreviewed', 'confirmed_by_reviewer', 'rejected', 'unknown'),
                    'invalid reviewed field')
            key = (hand['hand_id'], hand['table_id'], field['field'], field.get('slot'))
            require(key not in seen, 'duplicate review field')
            seen.add(key)
            if field['review_status'] != 'confirmed_by_reviewer':
                require(field.get('reviewer_value_unverified') is None, 'unreviewed claim has value')
                continue
            value = field.get('reviewer_value_unverified')
            require(type(value) is str and 1 <= len(value) <= 80,
                    'invalid reviewer claim')
            matches = []
            for obs in rows.get(key, []):
                if obs['human_selection_unverified'] != 'accepted' or obs['ocr_suggestion'] != value:
                    continue
                sha = obs['frame_sha256']
                if sha is None:
                    continue
                pts = frames.get((hand['hand_id'], hand['table_id'], sha))
                if pts is None or abs(pts - obs['pts_seconds']) > .25 or abs(pts - obs['frame_pts_seconds']) > .25:
                    continue
                matches.append({'observation_index': obs['observation_index'],
                                'pts_seconds': obs['pts_seconds'], 'frame_sha256': sha,
                                'ocr_confidence_raw_uncalibrated': obs['ocr_confidence_raw_uncalibrated']})
            matches.sort(key=lambda x: x['observation_index'])
            claims.append({'field': field['field'], 'slot': field.get('slot'),
                           'reviewer_value_unverified': value,
                           'status': ('frame_bytes_and_ocr_claim_linked_not_visual_truth' if matches
                                      else 'manual_or_unmatched_claim_requires_visual_review'),
                           'matching_frame_observations': matches,
                           'human_video_verification_required': True})
        results.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                        'claims': claims, 'math_ready': False, 'eligible_for_equity': False})
    require(hashes == [review.digest(p) for p in paths] and
            review.digest(Path(frame_directory) / 'manifest.json') == ocr['source_frame_manifest_sha256'],
            'source changed during audit')
    return {'schema_version': 1, 'status': 'offline_frame_evidence_link_audit_not_math_ready',
            'source_ocr_ledger_sha256': hashes[0],
            'source_reconstruction_sha256': hashes[1],
            'source_review_ledger_sha256': hashes[2],
            'source_frame_manifest_sha256': ocr['source_frame_manifest_sha256'],
            'source_video_sha256_claim': ocr['source_video_sha256_claim'],
            'source_video_hash_verified': verified_video_hash,
            'hand_count': len(results), 'hands': results,
            'claims_with_frame_links': sum(c['status'].startswith('frame_bytes') for h in results for c in h['claims']),
            'claims_without_frame_links': sum(c['status'].startswith('manual_or') for h in results for c in h['claims']),
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'video_content_not_semantically_verified': True,
            'warning': 'File hashes and timestamps establish provenance, not that any card/action is visible. No math eligibility.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ocr_ledger_json', 'reconstruction_json', 'review_ledger_json', 'frame_directory', 'new_audit_json'):
        parser.add_argument(name)
    parser.add_argument('--video', default=None)
    args = parser.parse_args(argv)
    target = Path(args.new_audit_json)
    sources = [Path(args.ocr_ledger_json), Path(args.reconstruction_json), Path(args.review_ledger_json),
               Path(args.frame_directory) / 'manifest.json']
    require(target.suffix == '.json' and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink() and target.resolve() not in {p.resolve() for p in sources},
            'output must be a new distinct JSON file')
    result = build(args.ocr_ledger_json, args.reconstruction_json, args.review_ledger_json,
                   args.frame_directory, args.video)
    with target.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    print(json.dumps({'hands': result['hand_count'],
                      'linked_claims': result['claims_with_frame_links'],
                      'unmatched_claims': result['claims_without_frame_links'],
                      'eligible_for_equity': 0, 'output': str(target)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
