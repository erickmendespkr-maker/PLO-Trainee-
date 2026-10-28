"""Bind *hypothetical* heads-up EV to one human-reviewed OFFLINE decision.

Usage:
 python offline_reviewed_decision_ev_link.py HANDS ACTION_AUDIT EV_SCENARIO EV_REPORT APPROVAL NEW_REPORT [--recording VIDEO]

Fail closed: recompute action audit and Monte Carlo EV from source inputs;
verify visible hero/board/pot/action references and the explicit human approval.
Does NOT authenticate the video, action completeness, opponent ranges, stack,
raise legality, or recommend a play. Never selects clips automatically.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile

import offline_four_table_action_timeline_audit as audit
import offline_omaha_conditional_ev as ev

SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_BYTES = 4 * 1024 * 1024
APPROVAL_KEYS = (
    'schema_version', 'source_hand_candidates_sha256',
    'source_action_audit_sha256', 'source_ev_scenario_sha256',
    'source_ev_report_sha256', 'reviewer_confirmed_offline',
    'hand_id', 'table_id', 'decision_id', 'hero_observation_index',
    'board_observation_index', 'pot_observation_index',
    'action_observation_index', 'observed_action_label',
    'heads_up_terminal_showdown_is_hypothesis', 'pot_units_reviewed',
    'call_cost_and_raise_are_hypotheses', 'reviewer_note',
)
CARD_BLOCKERS = {
    'hero_cards_changed_within_hand', 'conflicting_hero_same_timestamp',
    'conflicting_board_same_timestamp', 'board_shrank_within_hand',
    'board_changed_not_prefix', 'visible_hero_board_card_collision',
    'partial_board_not_a_street',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= MAX_BYTES, 'Missing, symlinked or oversized JSON')
    return json.loads(p.read_text(encoding='utf-8'),
                      object_pairs_hook=audit.unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def valid_approval(a, hashes):
    require(type(a) is dict and set(a) == set(APPROVAL_KEYS),
            'Invalid approval schema')
    require(type(a['schema_version']) is int and a['schema_version'] == 1,
            'Invalid approval version')
    for key, expected in zip(APPROVAL_KEYS[1:5], hashes):
        require(type(a[key]) is str and SHA.fullmatch(a[key]) and a[key] == expected,
                'Approval not bound to exact source hashes')
    for flag in ('reviewer_confirmed_offline',
                 'heads_up_terminal_showdown_is_hypothesis',
                 'pot_units_reviewed', 'call_cost_and_raise_are_hypotheses'):
        require(a[flag] is True, 'Missing explicit human/hypothesis approval')
    require(type(a['hand_id']) is str and audit.HAND_ID.fullmatch(a['hand_id']) and
            type(a['table_id']) is int and 1 <= a['table_id'] <= 4 and
            type(a['decision_id']) is str and 1 <= len(a['decision_id'].strip()) <= 1000 and
            type(a['reviewer_note']) is str and 1 <= len(a['reviewer_note'].strip()) <= 1000,
            'Invalid approval identity/note')
    indexes = [a[k] for k in ('hero_observation_index', 'board_observation_index',
                              'pot_observation_index', 'action_observation_index')]
    require(all(type(i) is int and 0 <= i < 32 for i in indexes) and
            len(set(indexes)) == 4, 'Invalid or reused observation index')
    require(type(a['observed_action_label']) is str and
            a['observed_action_label'] in ('fold', 'call', 'raise'),
            'Only reviewed fold/call/raise actions supported')


def validate_binding(hands, audited, scenario, a):
    require(type(hands) is dict and type(hands.get('hands')) is list and
            type(audited) is dict and type(audited.get('hands')) is list and
            hands.get('recording_sha256') == audited.get('recording_sha256'),
            'Invalid candidate/audit pair')
    require(type(hands.get('recording_sha256')) is str and
            SHA.fullmatch(hands['recording_sha256']), 'Invalid recording digest')
    matches = [(h, u) for h, u in zip(hands['hands'], audited['hands'])
               if h['hand_id'] == a['hand_id'] and h['table_id'] == a['table_id'] and
               u['hand_id'] == a['hand_id'] and u['table_id'] == a['table_id']]
    require(len(matches) == 1, 'Decision hand not uniquely found')
    h, u = matches[0]
    require(not any(issue['code'] in CARD_BLOCKERS for issue in u['review_flags']) and
            not h['same_timestamp_card_collisions'] and
            'hero_cards' not in h['changing_card_fields_needing_street_review'],
            'Unresolved card evidence conflict')
    require(u['action_history_complete'] is False and
            u['ready_for_equity_or_ev'] is False and
            h['complete_hand_reconstructed'] is False,
            'Unexpected upstream completeness claim')
    obs = {o['reviewed_candidate_index']: o for o in h['observations']}
    labels = ('hero_cards', 'board', 'pot', 'action')
    ids = [a[k] for k in ('hero_observation_index', 'board_observation_index',
                          'pot_observation_index', 'action_observation_index')]
    require(all(i in obs and obs[i]['field'] == field and
                obs[i]['review_decision'] in ('confirm', 'correct')
                for i, field in zip(ids, labels)),
            'Missing/mismatched reviewed observation')
    hero, board, pot, action = [obs[i] for i in ids]
    t = action['pts_seconds']
    require(hero['pts_seconds'] <= board['pts_seconds'] < t and
            pot['pts_seconds'] < t and t - pot['pts_seconds'] <= 5,
            'Stale/ambiguous pot or board relative to action')
    require(action['value'] == a['observed_action_label'],
            'Observed action label mismatch')
    require(scenario['decision_id'] == a['decision_id'] and
            scenario['call_scenario']['game_type'] == h['declared_game_type'] and
            scenario['call_scenario']['hero_hole'] == hero['value'].split() and
            scenario['call_scenario']['known_board'] == board['value'].split(),
            'EV snapshot differs from reviewed visible cards')
    require(Decimal(str(scenario['pot_before_decision'])) == Decimal(pot['value']),
            'EV pot differs from reviewed visible pot')
    # Require selected observations to be the last known state BEFORE action.
    for field, selected in (('hero_cards', hero), ('board', board), ('pot', pot)):
        later = [o for o in h['observations'] if o['field'] == field and
                 selected['pts_seconds'] < o['pts_seconds'] <= t]
        require(not later, 'A newer visible snapshot supersedes selected evidence')
    require(len([o for o in h['observations'] if o['field'] == 'action' and
                 o['pts_seconds'] == t]) == 1,
            'Multiple actions at the decision timestamp')
    require(not any(o['field'] in ('action', 'bet') and
                    pot['pts_seconds'] < o['pts_seconds'] < t
                    for o in h['observations']),
            'Intervening betting event may invalidate visible pot')
    # Require the same street candidate from the recomputed audit.
    audited_actions = [x for x in u['observed_action_labels']
                       if x['source_observation_index'] == ids[3]]
    require(len(audited_actions) == 1 and
            audited_actions[0]['action_label'] == action['value'] and
            audited_actions[0]['street_candidate'] is not None,
            'Decision street is ambiguous')
    return h, hero, board, pot, action, audited_actions[0]


def link(hands_path, audit_path, scenario_path, ev_report_path,
         approval_path, output_path, *, recording_path=None):
    sources = tuple(map(Path, (hands_path, audit_path, scenario_path,
                               ev_report_path, approval_path)))
    if recording_path is not None:
        sources += (Path(recording_path),)
    output = Path(output_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(output.resolve() != p.resolve() for p in sources),
            'Output must be new and distinct from inputs')
    # Digest all sources before computation; verify again after both recomputations.
    hashes = [audit.sha(p) if p.is_file() and not p.is_symlink() else None for p in sources]
    hands, prior_audit, scenario, prior_ev, approval = [read(p) for p in sources[:5]]
    valid_approval(approval, hashes[:4])
    with tempfile.TemporaryDirectory(prefix='plo_ev_audit_', dir=output.parent) as d:
        recomputed_audit = audit.build(sources[0], Path(d) / 'audit.json')
    if recording_path is not None:
        require(hashes[5] == hands['recording_sha256'],
                'Recording does not match reviewed candidate hash')
    require(prior_audit == recomputed_audit and
            prior_audit['source_hand_candidates_sha256'] == hashes[0],
            'Action audit differs from recomputed candidate audit')
    ev.validated(scenario)
    recomputed_ev = ev.calculate(scenario)
    recomputed_ev['source_scenario_sha256'] = hashes[2]
    require(prior_ev == recomputed_ev,
            'EV report differs from reproducible Monte Carlo calculation')
    h, hero, board, pot, action, street = validate_binding(
        hands, prior_audit, scenario, approval)
    require(all(audit.sha(p) == digest for p, digest in zip(sources, hashes)),
            'Source changed during audit/Monte Carlo recomputation')
    result = {
        'schema_version': 1,
        'analysis_status': 'reviewed_offline_decision_hypothetical_ev_link_only',
        'source_hand_candidates_sha256': hashes[0],
        'source_action_audit_sha256': hashes[1],
        'source_ev_scenario_sha256': hashes[2],
        'source_ev_report_sha256': hashes[3],
        'source_approval_sha256': hashes[4],
        'recording_sha256': hands['recording_sha256'],
        'recording_hash_checked_in_this_run': recording_path is not None,
        'hand_id': h['hand_id'], 'table_id': h['table_id'],
        'game_type': h['declared_game_type'],
        'decision_id': approval['decision_id'],
        'observed_action_label': action['value'],
        'action_pts_seconds': action['pts_seconds'],
        'street_candidate_not_confirmed': street['street_candidate'],
        'reviewed_observation_indices': dict(zip(('hero', 'board', 'pot', 'action'),
                                                 (approval[k] for k in
                                                  ('hero_observation_index', 'board_observation_index',
                                                   'pot_observation_index', 'action_observation_index')))),
        'source_crop_sha256': {k: o['source_crop_sha256'] for k, o in
                               zip(('hero', 'board', 'pot', 'action'),
                                   (hero, board, pot, action))},
        'pot_before_decision_as_reviewed': pot['value'],
        'conditional_ev_fold': prior_ev['ev_fold'],
        'conditional_ev_call': prior_ev['ev_call'],
        'conditional_ev_raise': prior_ev['ev_raise'],
        'conditional_ev_call_sampling_bounds': prior_ev['ev_call_sampling_bounds'],
        'conditional_ev_raise_sampling_and_fold_assumption_bounds':
            prior_ev['ev_raise_sampling_and_fold_assumption_bounds'],
        'call_range_assumption': scenario['call_scenario']['range_assumption'],
        'raise_called_range_assumption': scenario['raise_called_scenario']['range_assumption'],
        'fold_probability_hypothesis': prior_ev['fold_probability'],
        'reviewer_note': approval['reviewer_note'],
        'recomputed_ev_and_audit_from_supplied_inputs': True,
        'video_evidence_independently_verified': False,
        'action_history_complete': False,
        'raise_legality_verified': False,
        'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'warning': 'Conditional heads-up terminal-showdown EV only; review and SHA consistency '
                   'do not establish real-world action history, pot completeness, ranges, '
                   'stack sufficiency, raise legality, future betting or decision quality.',
    }
    with tempfile.TemporaryDirectory(prefix='plo_ev_link_', dir=output.parent) as d:
        staged = Path(d) / 'result.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n', encoding='utf-8')
        os.link(staged, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('hand_candidates', 'action_audit', 'ev_scenario', 'ev_report',
                 'human_approval', 'new_report'):
        parser.add_argument(name)
    parser.add_argument('--recording')
    args = parser.parse_args(argv)
    result = link(args.hand_candidates, args.action_audit, args.ev_scenario,
                  args.ev_report, args.human_approval, args.new_report,
                  recording_path=args.recording)
    print(json.dumps({'status': result['analysis_status'],
                      'hand_id': result['hand_id'],
                      'decision_id': result['decision_id']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
