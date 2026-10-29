"""Offline conditional PLO5/PLO6 equity report linked to an audited clip identity.

The reviewed card entry is an INDEPENDENT human assertion, never OCR inference.
The prior selected-action/ROI/clip binding is hash-checked, not replay-audited
again by this module. The selected OCR action is NOT graded; no hero attribution
is inferred. Monte Carlo confidence intervals describe sampling error ONLY.

Usage:
    python offline_reviewed_equity_clip_report.py BINDING_JSON CLIP_MP4 \
        MANUAL_REVIEW_JSON NEW_REPORT_JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from offline_plo_equity_monte_carlo import analyze, read_json, require

SHA = re.compile(r'[0-9a-f]{64}\Z')
HAND = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
REVIEW_FIELDS = {
    'schema_version', 'source_binding_sha256', 'source_clip_sha256',
    'hand_id', 'table_id', 'proposal_index', 'variant',
    'manual_cards_confirmed', 'review_method', 'review_notes',
    'hero_cards', 'board_cards', 'opponent_model', 'iterations', 'seed',
    'pot_now', 'call_cost', 'card_frame_evidence',
}
REQUIRED = {
    'schema_version', 'source_binding_sha256', 'source_clip_sha256',
    'hand_id', 'table_id', 'proposal_index', 'variant',
    'manual_cards_confirmed', 'review_method', 'review_notes',
    'hero_cards', 'board_cards', 'opponent_model', 'iterations', 'seed',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_file(path, *, max_bytes=None):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'unsafe or missing source file')
    require(p.stat().st_size > 0 and (max_bytes is None or p.stat().st_size <= max_bytes),
            'invalid source file size')
    return p


def sha_string(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def check_binding(binding):
    require(type(binding) is dict and type(binding.get('schema_version')) is int and binding.get('schema_version') == 1,
            'invalid evidence binding schema')
    require(binding.get('analysis_status') == 'offline_selected_action_roi_clip_identity_only',
            'wrong evidence binding type')
    require(binding.get('selected_action_to_replayed_roi_verified') is True and
            binding.get('selected_action_to_source_video_and_clip_verified') is True,
            'selected action has no replayed media identity')
    require(binding.get('ocr_semantics_verified') is False and
            binding.get('actor_identified') is False and
            binding.get('hands_reconstructed') is False and
            binding.get('ready_for_equity_or_ev') is False,
            'binding contains unsupported analysis claims')
    for key in ('roi_png_sha256', 'source_video_sha256', 'clip_sha256',
                'source_roi_ocr_report_sha256', 'source_timeline_sha256',
                'source_triage_sha256', 'source_clip_attestation_sha256'):
        require(sha_string(binding.get(key)), f'invalid {key}')
    require(type(binding.get('hand_id')) is str and HAND.fullmatch(binding['hand_id']),
            'invalid hand id')
    require(type(binding.get('table_id')) is int and 1 <= binding['table_id'] <= 4,
            'invalid table id')
    require(type(binding.get('proposal_index')) is int and
            0 <= binding['proposal_index'] <= 63, 'invalid proposal index')
    require(binding.get('variant') in ('PLO5', 'PLO6'), 'invalid variant')
    require(type(binding.get('timestamp_seconds')) in (int, float) and
            math.isfinite(binding['timestamp_seconds']) and
            0 <= binding['timestamp_seconds'] <= 4 * 3600,
            'invalid selected action timestamp')
    require(type(binding.get('reviewed_action_text')) is str and
            0 < len(binding['reviewed_action_text']) <= 128, 'invalid selected action')


def build(binding_path, clip_path, manual_path):
    binding_path = safe_file(binding_path, max_bytes=2_000_000)
    clip_path = safe_file(clip_path)
    manual_path = safe_file(manual_path, max_bytes=2_000_000)
    require(len({p.resolve() for p in (binding_path, clip_path, manual_path)}) == 3,
            'inputs must be different files')
    fingerprints = {str(p.resolve()): digest(p) for p in
                    (binding_path, clip_path, manual_path)}
    binding = read_json(binding_path)
    check_binding(binding)
    require(binding['clip_sha256'] == fingerprints[str(clip_path.resolve())],
            'clip does not match selected evidence binding')
    review = read_json(manual_path)
    require(type(review) is dict and REQUIRED <= set(review) <= REVIEW_FIELDS,
            'manual review missing required fields or contains unknown fields')
    require(type(review['schema_version']) is int and review['schema_version'] == 1,
            'invalid manual review schema')
    require(review['source_binding_sha256'] == fingerprints[str(binding_path.resolve())] and
            review['source_clip_sha256'] == fingerprints[str(clip_path.resolve())],
            'manual review source fingerprints do not match')
    for key in ('hand_id', 'table_id', 'proposal_index', 'variant'):
        require(type(review[key]) is type(binding[key]) and review[key] == binding[key],
                f'manual review identity mismatch: {key}')
    require(review['manual_cards_confirmed'] is True,
            'manual card confirmation required')
    require(review['review_method'] == 'manual_video_frame_review',
            'review method must explicitly state manual video/frame review')
    require(type(review['review_notes']) is str and
            8 <= len(review['review_notes'].strip()) <= 2000,
            'manual review notes must describe card evidence/uncertainty')
    require(('pot_now' in review) == ('call_cost' in review),
            'terminal EV requires both pot_now and call_cost')
    evidence = review.get('card_frame_evidence')
    if evidence is not None:
        require(type(evidence) is list and
                len(evidence) == len(review['hero_cards']) + len(review['board_cards']),
                'card/frame evidence must cover every reviewed card')
        seen_cards = set()
        for entry in evidence:
            require(type(entry) is dict and set(entry) == {'card', 'clip_timestamp_seconds'},
                    'invalid card/frame evidence record')
            card, stamp = entry['card'], entry['clip_timestamp_seconds']
            require(type(card) is str and card not in seen_cards,
                    'duplicate card/frame evidence')
            seen_cards.add(card)
            require(type(stamp) in (int, float) and math.isfinite(stamp) and
                    0 <= stamp <= 4*3600, 'invalid card/frame timestamp')
        require(seen_cards == set(review['hero_cards'] + review['board_cards']),
                'card/frame evidence does not match reviewed cards')
    payload = {key: review[key] for key in
               ('variant', 'hero_cards', 'board_cards', 'opponent_model',
                'iterations', 'seed')}
    payload['manual_review_confirmed'] = True
    if 'pot_now' in review:
        payload['pot_now'] = review['pot_now']
        payload['call_cost'] = review['call_cost']
    result = analyze(payload)
    require(all(digest(p) == h for p, h in fingerprints.items()),
            'source files changed during calculation')
    return {
        'schema_version': 1,
        'analysis_status': 'offline_conditional_manual_cards_equity_not_action_grade',
        'hand_id': binding['hand_id'], 'table_id': binding['table_id'],
        'variant': binding['variant'], 'proposal_index': binding['proposal_index'],
        'selected_action_timestamp_seconds': binding['timestamp_seconds'],
        'selected_action_ocr_text_not_graded': binding['reviewed_action_text'],
        'source_binding_sha256': fingerprints[str(binding_path.resolve())],
        'source_clip_sha256': fingerprints[str(clip_path.resolve())],
        'source_manual_review_sha256': fingerprints[str(manual_path.resolve())],
        'source_video_sha256_claim_from_binding': binding['source_video_sha256'],
        'binding_replay_audit_rerun': False,
        'manual_cards_claimed_reviewed_not_independently_verified': True,
        'card_frame_evidence_claimed_not_independently_verified': evidence is not None,
        'card_frame_evidence_count': len(evidence) if evidence is not None else 0,
        'hero_actor_at_selected_action_verified': False,
        'selected_action_strategic_correctness_verified': False,
        'ocr_semantics_verified': False,
        'opponent_range_is_assumption': True,
        'equity_result': result,
        'warning': ('Conditional equity for manually entered cards and assumed range only. '
                    'No inference that selected OCR action belongs to hero, no action grade. '
                    'Binding replay was NOT rerun; hashes link to prior evidence. '
                    'Card/frame timestamps are human claims, not verified visual recognition. '
                    'Sampling CI excludes card/range/model uncertainty.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binding_json')
    parser.add_argument('clip_mp4')
    parser.add_argument('manual_review_json')
    parser.add_argument('new_report_json')
    args = parser.parse_args(argv)
    out = Path(args.new_report_json)
    require(out.parent.is_dir() and not out.parent.is_symlink() and
            not out.exists() and not out.is_symlink() and out.suffix == '.json',
            'output must be a new JSON file')
    require(out.resolve() not in {Path(p).resolve() for p in
            (args.binding_json, args.clip_mp4, args.manual_review_json)},
            'cannot overwrite evidence')
    report = build(args.binding_json, args.clip_mp4, args.manual_review_json)
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    print(json.dumps({'analysis_status': report['analysis_status'],
                      'equity': report['equity_result']['equity'],
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
