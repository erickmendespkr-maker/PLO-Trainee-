"""Consolidate offline PLO5/PLO6 hand/street and visual-review ledgers.

Usage: python offline_visual_hand_summary.py REVIEWED.json VISUAL.json NEW_SUMMARY.json

All OCR and reviewer values remain unauthenticated assertions. This is a
human-readable diagnostic artifact, NEVER a Monte Carlo input or EV verdict.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import offline_hand_street_review as source

STREETS = ('preflop', 'flop', 'turn', 'river', 'unknown')
VISUAL = ('uncertain', 'not_visible', 'seen_by_reviewer')
FIELDS = ('hero_card', 'board_card', 'action', 'pot', 'stack', 'variant')
MAX_CLAIMS = 1600


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def strict_equal(a, b):
    """JSON equality without Python's True == 1 trap."""
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, allow_nan=False)


def build(reviewed, visual, reviewed_sha, visual_sha):
    require(type(reviewed_sha) is str and source.SHA.fullmatch(reviewed_sha) and
            type(visual_sha) is str and source.SHA.fullmatch(visual_sha), 'invalid source hashes')
    require(type(reviewed) is dict and reviewed.get('schema_version') == 1 and
            reviewed.get('status') == 'offline_hand_street_review_import_unverified_not_math_ready' and
            reviewed.get('reviewer_claims_not_authenticated') is True and
            reviewed.get('original_video_cards_not_independently_verified') is True and
            type(reviewed.get('eligible_for_equity')) is int and reviewed['eligible_for_equity'] == 0 and
            reviewed.get('equity_or_ev_calculated') is False and
            type(reviewed.get('hands')) is list and 1 <= len(reviewed['hands']) <= 100 and
            type(reviewed.get('hand_count')) is int and reviewed['hand_count'] == len(reviewed['hands']) and
            type(reviewed.get('source_video_sha256_claim')) is str and
            source.SHA.fullmatch(reviewed['source_video_sha256_claim']), 'invalid reviewed ledger')
    require(type(visual) is dict and visual.get('schema_version') == 1 and
            visual.get('status') == 'offline_visual_evidence_import_unverified_not_math_ready' and
            visual.get('source_review_sha256') == reviewed_sha and
            visual.get('source_video_sha256_claim') == reviewed['source_video_sha256_claim'] and
            visual.get('reviewer_claims_not_authenticated') is True and
            visual.get('video_content_not_semantically_verified') is True and
            type(visual.get('eligible_for_equity')) is int and visual['eligible_for_equity'] == 0 and
            visual.get('equity_or_ev_calculated') is False and
            type(visual.get('claims')) is list and len(visual['claims']) <= MAX_CLAIMS and
            type(visual.get('claim_count')) is int and visual['claim_count'] == len(visual['claims']),
            'invalid or unbound visual ledger')
    require(type(visual.get('source_frame_manifest_sha256')) is str and
            source.SHA.fullmatch(visual['source_frame_manifest_sha256']), 'invalid manifest hash')
    claims = {}
    status_counts = {s: 0 for s in VISUAL}
    for c in visual['claims']:
        require(type(c) is dict and type(c.get('hand_id')) is str and source.ID.fullmatch(c['hand_id']) and
                type(c.get('table_id')) is str and source.ID.fullmatch(c['table_id']) and
                c.get('field') in FIELDS and type(c.get('slot')) in (int, type(None)) and
                (c['slot'] is None or 0 <= c['slot'] <= 5) and
                type(c.get('value_unverified')) is str and
                1 <= len(c['value_unverified']) <= 80 and
                c.get('visual_review_status_unverified') in VISUAL and
                c.get('video_content_semantically_verified') is False and
                c.get('math_ready') is False and
                type(c.get('evidence')) is list and len(c['evidence']) <= 12,
                'invalid visual claim')
        key = (c['hand_id'], c['table_id'], c['field'], c['slot'])
        require(key not in claims, 'duplicate visual claim')
        pts = []
        seen_obs = set()
        for e in c['evidence']:
            require(type(e) is dict and set(e) == {'frame_sha256', 'pts_seconds', 'observation_index'} and
                    type(e['frame_sha256']) is str and source.SHA.fullmatch(e['frame_sha256']) and
                    type(e['pts_seconds']) in (int, float) and math.isfinite(e['pts_seconds']) and
                    0 <= e['pts_seconds'] <= 14400 and
                    type(e['observation_index']) is int and e['observation_index'] >= 0,
                    'invalid frame evidence')
            identity = (e['frame_sha256'], e['pts_seconds'], e['observation_index'])
            require(identity not in seen_obs, 'duplicate frame evidence')
            seen_obs.add(identity)
            pts.append(e['pts_seconds'])
        require(c['visual_review_status_unverified'] != 'seen_by_reviewer' or pts,
                'seen claim without frame evidence')
        claims[key] = {'value': c['value_unverified'],
                       'status': c['visual_review_status_unverified'], 'pts_seconds': pts}
        status_counts[c['visual_review_status_unverified']] += 1
    hands = []
    expected = set()
    total_fields = 0
    confirmed_count = 0
    tables = set()
    for hand in reviewed['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str and source.ID.fullmatch(hand['hand_id']) and
                type(hand.get('table_id')) is str and source.ID.fullmatch(hand['table_id']) and
                type(hand.get('fields')) is list and len(hand['fields']) <= 16 and
                hand.get('math_ready') is False and hand.get('eligible_for_equity') is False,
                'invalid reviewed hand')
        identity = (hand['hand_id'], hand['table_id'])
        require(identity not in {(h['hand_id'], h['table_id']) for h in hands}, 'duplicate reviewed hand')
        tables.add(hand['table_id'])
        streets = {s: {'fields': 0, 'declared': 0, 'seen_unverified': 0, 'uncertain': 0, 'not_visible': 0} for s in STREETS}
        fields = []
        hand_keys = set()
        declared_cards = []
        variant = None
        for f in hand['fields']:
            total_fields += 1
            require(total_fields <= MAX_CLAIMS and type(f) is dict and f.get('field') in FIELDS and
                    f.get('street') in STREETS and type(f.get('slot')) in (int, type(None)) and
                    (f['slot'] is None or 0 <= f['slot'] <= 5) and
                    f.get('review_status') in ('unreviewed', 'confirmed_by_reviewer', 'rejected', 'unknown'),
                    'invalid reviewed field')
            key = (hand['hand_id'], hand['table_id'], f['field'], f['slot'])
            require(key not in hand_keys, 'duplicate reviewed field')
            hand_keys.add(key)
            st = streets[f['street']]
            st['fields'] += 1
            if f['review_status'] == 'confirmed_by_reviewer':
                confirmed_count += 1
                st['declared'] += 1
                value = f.get('reviewer_value_unverified')
                require(type(value) is str and 1 <= len(value) <= 80, 'invalid confirmed value')
                expected.add(key)
                require(key in claims and claims[key]['value'] == value, 'visual claim differs from reviewed declaration')
                state = claims[key]['status']
                st['seen_unverified' if state == 'seen_by_reviewer' else state] += 1
                if f['field'] in ('hero_card', 'board_card'):
                    declared_cards.append(value)
                if f['field'] == 'variant':
                    variant = value
                fields.append({'field': f['field'], 'slot': f['slot'], 'street': f['street'],
                               'reviewer_value_unverified': value,
                               'visual_status_unverified': state,
                               'evidence_pts_seconds': claims[key]['pts_seconds']})
            else:
                require(f.get('reviewer_value_unverified') is None, 'unconfirmed field has value')
        blockers = ['video_content_not_independently_verified', 'opponent_ranges_not_supplied']
        if variant not in ('PLO5', 'PLO6'):
            blockers.append('variant_not_confirmed')
        if len(declared_cards) != len(set(declared_cards)):
            blockers.append('duplicate_declared_card')
        if any(x['visual_status_unverified'] != 'seen_by_reviewer' for x in fields):
            blockers.append('visual_review_incomplete')
        if any(f['street'] == 'unknown' and f['field'] == 'action' for f in fields):
            blockers.append('action_street_unverified')
        hands.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                      'streets': streets, 'declared_fields': fields,
                      'blockers': sorted(set(blockers)),
                      'eligible_for_equity': False, 'math_ready': False})
    require(len(tables) <= 4 and set(claims) == expected and
            type(reviewed.get('field_count')) is int and reviewed['field_count'] == total_fields and
            type(reviewed.get('reviewer_declarations_unverified')) is int and
            reviewed['reviewer_declarations_unverified'] == confirmed_count,
            'visual/review field coverage mismatch')
    require(visual.get('seen_by_reviewer_unverified') == status_counts['seen_by_reviewer'] and
            visual.get('not_visible_by_reviewer_unverified') == status_counts['not_visible'] and
            visual.get('uncertain') == status_counts['uncertain'], 'visual status counters mismatch')
    return {'schema_version': 1, 'status': 'offline_hand_visual_summary_unverified_not_math_ready',
            'source_review_sha256': reviewed_sha, 'source_visual_ledger_sha256': visual_sha,
            'source_video_sha256_claim': reviewed['source_video_sha256_claim'],
            'source_frame_manifest_sha256': visual['source_frame_manifest_sha256'],
            'hand_count': len(hands), 'declared_field_count': confirmed_count,
            'visual_status_counts': status_counts, 'hands': hands,
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'reviewer_claims_not_authenticated': True,
            'video_content_not_semantically_verified': True,
            'warning': 'Review assertions and frame links are not visual truth; no equity or EV can be inferred.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_json')
    parser.add_argument('visual_ledger_json')
    parser.add_argument('new_summary_json')
    args = parser.parse_args(argv)
    sources = [Path(args.reviewed_json), Path(args.visual_ledger_json)]
    target = Path(args.new_summary_json)
    require(target.suffix == '.json' and target.parent.is_dir() and not target.parent.is_symlink() and
            not target.exists() and not target.is_symlink() and
            target.resolve() not in {p.resolve() for p in sources}, 'output must be new and distinct')
    before = [source.digest(p) for p in sources]
    result = build(source.read(sources[0]), source.read(sources[1]), *before)
    require(before == [source.digest(p) for p in sources], 'source changed during summary')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'hands': result['hand_count'], 'declared_fields': result['declared_field_count'],
                      'eligible_for_equity': 0, 'output': str(target)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
