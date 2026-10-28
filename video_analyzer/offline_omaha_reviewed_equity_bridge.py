"""Offline fail-closed bridge: reviewed *visible* PLO5/PLO6 snapshots -> conditional equity.

Usage: python offline_omaha_reviewed_equity_bridge.py HANDS_JSON AUDIT_JSON APPROVAL_JSON NEW_REPORT_JSON [--recording MP4]

No inference of hidden cards, action completeness, EV, or clip authorization.
Human-supplied opponent combinations remain hypotheses, not observations.
Recomputes the upstream action audit and checks source hashes before Monte Carlo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import offline_four_table_action_timeline_audit as audit
import offline_omaha_equity_mc as mc

MAX_BYTES = 4 * 1024 * 1024


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    p = Path(path)
    check(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
          'Missing, symlinked, empty or oversized JSON')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=mc.no_duplicate_json_keys,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def strict(obj, keys):
    check(type(obj) is dict and set(obj) == set(keys), 'Unexpected or missing JSON fields')


def bridge(hands_path, audit_path, approval_path, output_path, *, recording_path=None):
    sources = [Path(hands_path), Path(audit_path), Path(approval_path)]
    if recording_path is not None:
        sources.append(Path(recording_path))
    output = Path(output_path)
    check(output.parent.is_dir() and not output.parent.is_symlink() and
          not output.exists() and not output.is_symlink() and
          all(output.resolve() != p.resolve() for p in sources),
          'Output must be a new, separate file')
    before = [sha(p) if p.is_file() and not p.is_symlink() else None for p in sources]
    hands, prior_audit, approval = (read(p) for p in sources[:3])
    # Verify the upstream candidate contract and recompute the action audit.
    # A claimed readiness flag or edited audit is never sufficient.
    with tempfile.TemporaryDirectory(prefix='plo_bridge_check_', dir=output.parent) as d:
        recomputed = audit.build(sources[0], Path(d) / 'audit.json',
                                 recording_path=recording_path)
    check(prior_audit == recomputed and
          prior_audit['source_hand_candidates_sha256'] == before[0],
          'Action audit does not match verified candidate input')
    strict(approval, ('schema_version', 'source_hand_candidates_sha256',
                      'source_action_audit_sha256', 'reviewer_confirmed_offline',
                      'hand_id', 'table_id', 'hero_observation_index',
                      'board_observation_index', 'explicit_villain_hands',
                      'range_assumption', 'samples', 'seed', 'reviewer_note'))
    check(type(approval['schema_version']) is int and approval['schema_version'] == 1 and
          approval['source_hand_candidates_sha256'] == before[0] and
          approval['source_action_audit_sha256'] == before[1] and
          approval['reviewer_confirmed_offline'] is True and
          type(approval['hand_id']) is str and
          type(approval['table_id']) is int and 1 <= approval['table_id'] <= 4 and
          type(approval['reviewer_note']) is str and
          1 <= len(approval['reviewer_note'].strip()) <= 1000,
          'Approval not explicitly bound to input evidence')
    matches = [(h, a) for h, a in zip(hands['hands'], prior_audit['hands'])
               if h['hand_id'] == approval['hand_id'] and
               h['table_id'] == approval['table_id'] and
               a['hand_id'] == approval['hand_id'] and
               a['table_id'] == approval['table_id'] and
               a['declared_game_type'] == h['declared_game_type']]
    check(len(matches) == 1, 'Approved hand not found uniquely')
    hand, audited = matches[0]
    blocked_codes = {'hero_cards_changed_within_hand', 'conflicting_hero_same_timestamp',
                     'conflicting_board_same_timestamp', 'board_shrank_within_hand',
                     'board_changed_not_prefix', 'visible_hero_board_card_collision',
                     'partial_board_not_a_street'}
    check(not any(issue['code'] in blocked_codes for issue in audited['review_flags']) and
          not hand['same_timestamp_card_collisions'] and
          'hero_cards' not in hand['changing_card_fields_needing_street_review'],
          'Unresolved visible card conflict')
    indexes = (approval['hero_observation_index'], approval['board_observation_index'])
    check(all(type(i) is int and 0 <= i < 32 for i in indexes) and
          indexes[0] != indexes[1], 'Invalid observation indices')
    observed = {o['reviewed_candidate_index']: o for o in hand['observations']}
    check(all(i in observed for i in indexes), 'Approved observations absent')
    hero, board = (observed[i] for i in indexes)
    check(hero['field'] == 'hero_cards' and board['field'] == 'board' and
          hero['review_decision'] in ('confirm', 'correct') and
          board['review_decision'] in ('confirm', 'correct') and
          hero['pts_seconds'] <= board['pts_seconds'],
          'Hero/board evidence does not match approved fields or chronology')
    scenario = {'schema_version': 1, 'game_type': hand['declared_game_type'],
                'hero_hole': hero['value'].split(' '),
                'known_board': board['value'].split(' '),
                'explicit_villain_hands': approval['explicit_villain_hands'],
                'samples': approval['samples'], 'seed': approval['seed'],
                'range_assumption': approval['range_assumption']}
    mc.validate_scenario(scenario)
    result = mc.estimate(scenario)
    check(all(sha(p) == digest for p, digest in zip(sources, before)),
          'Input changed during computation')
    result.update({
        'analysis_status': 'reviewed_visible_snapshot_conditional_equity_only',
        'source_hand_candidates_sha256': before[0],
        'source_action_audit_sha256': before[1],
        'source_approval_sha256': before[2],
        'recording_sha256': hands['recording_sha256'],
        'recording_hash_checked_in_this_run': recording_path is not None,
        'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
        'hero_evidence': {'source_observation_index': indexes[0],
                          'pts_seconds': hero['pts_seconds'],
                          'source_crop_sha256': hero['source_crop_sha256']},
        'board_evidence': {'source_observation_index': indexes[1],
                           'pts_seconds': board['pts_seconds'],
                           'source_crop_sha256': board['source_crop_sha256']},
        'reviewer_note': approval['reviewer_note'],
        'video_evidence_verified': False, 'complete_hand_reconstructed': False,
        'ready_for_ev': False, 'automatic_clip_selection_authorized': False,
        'warning': 'Conditional showdown equity on manually reviewed visible snapshots. '
                   'Upstream hashes do not independently authenticate the video or reviewer. '
                   'Opponent range is hypothetical; missing actions and future betting prevent EV.'
    })
    with tempfile.TemporaryDirectory(prefix='plo_bridge_out_', dir=output.parent) as d:
        stage = Path(d) / 'result.json'
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                         encoding='utf-8')
        os.link(stage, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('hand_candidates', 'action_audit', 'human_approval', 'new_report'):
        parser.add_argument(arg)
    parser.add_argument('--recording')
    a = parser.parse_args(argv)
    r = bridge(a.hand_candidates, a.action_audit, a.human_approval, a.new_report,
               recording_path=a.recording)
    print(json.dumps({'status': r['analysis_status'], 'equity': r['equity_estimate'],
                      'samples': r['samples']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
