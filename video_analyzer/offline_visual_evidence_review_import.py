"""Fail-closed importer of UNTRUSTED visual-review drafts for recorded PLO5/PLO6.

Usage: python offline_visual_evidence_review_import.py OCR.json RECON.json REVIEW.json FRAMES_DIR DRAFT.json NEW_LEDGER.json

Recomputes the visual packet from source bytes; accepts only reviewer status/note
changes. A 'seen' claim remains a human assertion, never video truth or math input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import offline_hand_street_review as review
import offline_hand_frame_evidence_audit as audit
import offline_visual_evidence_review_ui as visual

STATUSES = {'uncertain', 'not_visible', 'seen_by_reviewer'}
MAX_CLAIMS = 1600


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identical(a, b):
    """Type-sensitive JSON equality: unlike Python, true must not equal 1."""
    return json.dumps(a, sort_keys=True, ensure_ascii=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=True, allow_nan=False)


def build(ocr_path, reconstruction_path, reviewed_path, frames_dir, draft_path):
    sources = [Path(p) for p in (ocr_path, reconstruction_path, reviewed_path, draft_path)]
    before = [review.digest(p) for p in sources]
    manifest_path = Path(frames_dir) / 'manifest.json'
    manifest_before = review.digest(manifest_path)
    packet = visual.build(ocr_path, reconstruction_path, reviewed_path, frames_dir)
    draft = review.read(draft_path)
    require(type(draft) is dict and set(draft) == {
        'schema_version', 'status', 'source_review_sha256',
        'source_frame_manifest_sha256', 'source_video_sha256_claim',
        'reviewer_claims_not_authenticated', 'math_ready', 'eligible_for_equity',
        'equity_or_ev_calculated', 'claims'}, 'invalid visual draft root')
    expected_root = {
        'schema_version': 1, 'status': 'offline_visual_review_untrusted_draft',
        'source_review_sha256': packet['source_review_sha256'],
        'source_frame_manifest_sha256': packet['source_frame_manifest_sha256'],
        'source_video_sha256_claim': packet['source_video_sha256_claim'],
        'reviewer_claims_not_authenticated': True, 'math_ready': False,
        'eligible_for_equity': 0, 'equity_or_ev_calculated': False}
    require(all(identical(draft[k], v) for k, v in expected_root.items()),
            'visual draft provenance or safety flags changed')
    require(type(draft['claims']) is list and len(draft['claims']) == len(packet['cards'])
            and len(draft['claims']) <= MAX_CLAIMS, 'visual claim count mismatch')
    results = []
    for raw, original in zip(draft['claims'], packet['cards']):
        require(type(raw) is dict and set(raw) == {
            'hand_id', 'table_id', 'field', 'slot', 'value_unverified',
            'visual_review_status', 'reviewer_note', 'evidence'}, 'invalid visual claim fields')
        expected = {
            'hand_id': original['hand_id'], 'table_id': original['table_id'],
            'field': original['field'], 'slot': original['slot'],
            'value_unverified': original['value_unverified'],
            'evidence': [{'frame_sha256': e['sha256'], 'pts_seconds': e['pts'],
                          'observation_index': e['observation_index']}
                         for e in original['evidence']]}
        require(all(identical(raw[k], v) for k, v in expected.items()),
                'visual claim identity or evidence altered')
        status, note = raw['visual_review_status'], raw['reviewer_note']
        require(type(status) is str and status in STATUSES, 'invalid visual review status')
        require(type(note) is str and len(note) <= 500 and
                all(c in '\n\t' or ord(c) >= 32 and ord(c) != 127 for c in note),
                'invalid reviewer note')
        require(status != 'seen_by_reviewer' or len(expected['evidence']) > 0,
                'cannot mark unseen evidence as seen')
        results.append({**expected, 'visual_review_status_unverified': status,
                        'reviewer_note_unverified': note,
                        'video_content_semantically_verified': False,
                        'math_ready': False})
    require(before == [review.digest(p) for p in sources] and
            manifest_before == review.digest(manifest_path), 'input changed during import')
    # Revalidate all saved PNG bytes at the end to catch changes during review.
    audit.validate_manifest(Path(frames_dir), review.read(ocr_path))
    return {'schema_version': 1, 'status': 'offline_visual_evidence_import_unverified_not_math_ready',
            'source_ocr_sha256': before[0], 'source_reconstruction_sha256': before[1],
            'source_review_sha256': before[2], 'source_visual_draft_sha256': before[3],
            'source_frame_manifest_sha256': manifest_before,
            'source_video_sha256_claim': packet['source_video_sha256_claim'],
            'claim_count': len(results),
            'seen_by_reviewer_unverified': sum(x['visual_review_status_unverified'] == 'seen_by_reviewer' for x in results),
            'not_visible_by_reviewer_unverified': sum(x['visual_review_status_unverified'] == 'not_visible' for x in results),
            'uncertain': sum(x['visual_review_status_unverified'] == 'uncertain' for x in results),
            'claims': results, 'reviewer_claims_not_authenticated': True,
            'video_content_not_semantically_verified': True,
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'warning': 'Human visual review is an unauthenticated assertion, not video truth. No equity/EV eligibility.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ocr', 'reconstruction', 'reviewed', 'frames_dir', 'draft', 'new_ledger'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    target = Path(args.new_ledger)
    sources = [Path(p) for p in (args.ocr, args.reconstruction, args.reviewed, args.draft)]
    sources.append(Path(args.frames_dir) / 'manifest.json')
    require(target.suffix == '.json' and target.parent.is_dir() and not target.parent.is_symlink()
            and not target.exists() and not target.is_symlink()
            and target.resolve() not in {p.resolve() for p in sources},
            'output must be a new distinct JSON file')
    result = build(args.ocr, args.reconstruction, args.reviewed, args.frames_dir, args.draft)
    with target.open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({'claims': result['claim_count'],
                      'seen_unverified': result['seen_by_reviewer_unverified'],
                      'eligible_for_equity': 0, 'output': str(target)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
