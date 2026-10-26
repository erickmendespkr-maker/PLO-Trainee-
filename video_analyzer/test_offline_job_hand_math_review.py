"""Synthetic-only verification for the fail-closed offline math review bridge."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline_job_hand_math_review import (make_worksheet, run_review, digest,
                                          export_template, export_math)


def source_hand(variant='PLO5', table=1, label='H1', complete=True):
    hero = ['As', 'Kh', 'Qd', 'Jc', 'Ts'] + (['5d'] if variant == 'PLO6' else [])
    entry = {
        'table_id': table, 'hand_label_human_assigned': label,
        'variant': variant, 'hero_cards': hero if complete else None,
        'board_by_street': {'flop': ['2c', '3d', '4h'], 'turn': '5s', 'river': '6c'},
        'actions': [{'street': 'preflop', 'actor': 'hero', 'action': 'call',
                     'amount': 20, 'source_pts_seconds': 1},
                    {'street': 'flop', 'actor': 'villain_1', 'action': 'bet',
                     'amount': 50, 'source_pts_seconds': 3},
                    {'street': 'flop', 'actor': 'hero', 'action': 'call',
                     'amount': 50, 'source_pts_seconds': 4}],
        'pot_before_decision': 100, 'call_amount': 50, 'effective_stack': 300,
        'source_pts_start_seconds': 0, 'source_pts_end_seconds': 10,
        'source_pts_checked_by_human': True, 'reviewer_attestation': True,
        'opponent_range_notes': 'Hypothetical range, synthetic only',
        'notes': 'Synthetic fixture, not a real video', 'confidence_subjective': .7,
    }
    return {
        'table_id': table, 'hand_label_human_assigned': label,
        'source_nominal_interval_seconds': [0, 10],
        'source_image_sha256s': ['a' * 64], 'human_entry': entry,
        'status': ('structurally_complete_human_draft_unverified' if complete
                   else 'incomplete_human_draft_unverified'),
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
    }


def source(variant='PLO5', complete=True):
    return {
        'schema_version': 1, 'analysis_status': 'human_entered_hand_history_drafts_no_math',
        'job_id': 'b' * 32, 'source_sha256': 'c' * 64,
        'source_checklist_sha256': 'd' * 64,
        'timestamp_semantics': 'human_claimed_pts_not_independently_verified',
        'hands': [source_hand(variant, complete=complete)],
        'counts': {'hands': 1, 'structurally_complete_unverified': int(complete), 'math_ready': 0},
        'requires_source_video_reaudit': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
    }


def filled_scenario(worksheet, variant='PLO5'):
    filled = copy.deepcopy(worksheet)
    form = filled['tasks'][0]['manual_scenario_draft']
    form.update(timestamp=4, human_confirmed=True, observation_confidence=.8,
                monte_carlo_trials=80, monte_carlo_seed=12345,
                model_notes='Explicit hypothetical opponent range and all-in model')
    form['model_assumptions'].update(heads_up=True, all_in_no_future_betting=True,
                                     no_rake=True, no_side_pots=True, no_icm=True)
    hero = ['As', 'Kh', 'Qd', 'Jc', 'Ts'] + (['5d'] if variant == 'PLO6' else [])
    vals = {'hero_cards': hero, 'board': ['2c', '3d', '4h'],
            'observed_action': 'call', 'pot_before_action': 100, 'call_amount': 50}
    for field, value in vals.items():
        form['reviewed_fields'][field] = {
            'value': value, 'confidence': .8, 'source_timestamp': 4,
            'source': 'independent_manual_video_review', 'human_confirmed': True,
        }
    cards = ['9c', '9d', '8h', '7s', '6d'] + (['8c'] if variant == 'PLO6' else [])
    form['call_range'] = [{'cards': cards, 'weight': 1.0}]
    return filled


class MathReviewTests(unittest.TestCase):
    def setup_case(self, variant='PLO5', complete=True):
        s = source(variant, complete)
        w = make_worksheet(s, digest(s))
        f = filled_scenario(w, variant)
        return s, w, f

    def test_template_empty_and_blocked(self):
        s, w, _ = self.setup_case()
        self.assertIsNone(w['tasks'][0]['manual_scenario_draft']['timestamp'])
        self.assertFalse(w['ready_for_equity_or_ev'])
        self.assertFalse(w['automatic_clip_selection_authorized'])

    def test_plo5_equity_and_ev_reproducible(self):
        s, w, f = self.setup_case()
        a = run_review(s, w, f, digest(s))
        b = run_review(s, w, f, digest(s))
        self.assertEqual(a, b)
        self.assertEqual(a['counts']['hypothetical'], 1)
        r = a['results'][0]
        self.assertEqual(r['status'], 'hypothetical_only_not_video_verified')
        self.assertEqual(r['variant'], 'PLO5')
        self.assertEqual(r['trials'], 80)
        self.assertTrue(0 <= r['equity'] <= 1)
        self.assertFalse(a['strategic_error_established'])
        self.assertFalse(a['automatic_clip_selection_authorized'])

    def test_plo6_equity(self):
        s, w, f = self.setup_case('PLO6')
        result = run_review(s, w, f, digest(s))
        self.assertEqual(result['results'][0]['variant'], 'PLO6')

    def test_plo5_raise_model_hypothetical(self):
        s, _, _ = self.setup_case()
        s['hands'][0]['human_entry']['actions'][-1]['action'] = 'raise'
        s['hands'][0]['human_entry']['actions'][-1]['amount'] = 150
        w = make_worksheet(s, digest(s))
        f = filled_scenario(w)
        form = f['tasks'][0]['manual_scenario_draft']
        form['reviewed_fields']['observed_action']['value'] = 'raise'
        form['fold_probability'] = .25
        form['model_assumptions']['hero_extra_chips'] = 150
        form['model_assumptions']['villain_extra_chips_if_called'] = 100
        r = run_review(s, w, f, digest(s))
        self.assertEqual(r['counts']['hypothetical'], 1)
        self.assertEqual(r['results'][0]['observed_action_assumed'], 'raise')
        self.assertFalse(r['strategic_error_established'])

    def test_action_mismatch_blocked(self):
        def mutate(s, w, f):
            form = f['tasks'][0]['manual_scenario_draft']
            form['reviewed_fields']['observed_action']['value'] = 'raise'
            form['fold_probability'] = .2
            form['model_assumptions']['hero_extra_chips'] = 150
            form['model_assumptions']['villain_extra_chips_if_called'] = 100
        self.blocked(mutate, 'documented hero action')

    def test_field_timestamp_outside_hand(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['hero_cards'].__setitem__('source_timestamp', 99), 'outside span')

    def test_no_field_attestation(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['hero_cards'].__setitem__('human_confirmed', False), 'attestation')

    def test_reject_duplicate_hand_source(self):
        s, w, f = self.setup_case()
        s['hands'].append(copy.deepcopy(s['hands'][0]))
        s['counts'] = {'hands': 2, 'structurally_complete_unverified': 2, 'math_ready': 0}
        with self.assertRaisesRegex(ValueError, 'Duplicate hand'):
            run_review(s,w,f,digest(s))

    def test_reject_unauthorized_row(self):
        s, w, f = self.setup_case()
        s['hands'][0]['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'cannot authorize'):
            run_review(s,w,f,digest(s))

    def test_incomplete_hand_blocked(self):
        s, w, f = self.setup_case(complete=False)
        result = run_review(s, w, f, digest(s))
        self.assertEqual(result['counts']['hypothetical'], 0)
        self.assertEqual(result['results'][0]['status'], 'blocked_incomplete_hand_draft')

    def test_empty_form_skipped(self):
        s, w, _ = self.setup_case()
        result = run_review(s, w, copy.deepcopy(w), digest(s))
        self.assertEqual(result['counts']['skipped'], 1)

    def test_four_tables_isolated(self):
        s = source()
        s['hands'] = [source_hand(table=i, label=f'H{i}') for i in (4, 2, 1, 3)]
        s['counts'] = {'hands': 4, 'structurally_complete_unverified': 4, 'math_ready': 0}
        w = make_worksheet(s, digest(s))
        self.assertEqual([t['table_id'] for t in w['tasks']], [4, 2, 1, 3])
        self.assertEqual(run_review(s, w, w, digest(s))['counts']['skipped'], 4)

    def blocked(self, mutate, reason='.'):
        s, w, f = self.setup_case()
        mutate(s, w, f)
        r = run_review(s, w, f, digest(s))
        self.assertEqual(r['counts']['hypothetical'], 0)
        self.assertRegex(r['results'][0]['reason'], reason)

    def test_conflicting_hero_cards(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['hero_cards']['value'].__setitem__(0, 'Ac'), 'hero cards')

    def test_conflicting_board(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['board']['value'].__setitem__(0, '2d'), 'board')

    def test_conflicting_pot(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['pot_before_action'].__setitem__('value', 999), 'chip amounts')

    def test_conflicting_call(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['reviewed_fields']['call_amount'].__setitem__('value', 30), 'chip amounts')

    def test_unmatched_decision_pts(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft'].__setitem__('timestamp', 4.5), 'documented hero action')

    def test_invalid_range_overlap(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['call_range'][0]['cards'].__setitem__(0, 'As'), 'Duplicate')

    def test_bad_seed(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft'].__setitem__('monte_carlo_seed', True), 'seed')

    def test_missing_manual_attestation(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft'].__setitem__('human_confirmed', False), 'attested')

    def test_no_range(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft'].__setitem__('call_range', []), 'range')

    def test_no_model_assumptions(self):
        self.blocked(lambda s,w,f: f['tasks'][0]['manual_scenario_draft']['model_assumptions'].__setitem__('no_rake', False), 'assumptions')

    def test_protected_metadata_tampering(self):
        s,w,f = self.setup_case()
        f['tasks'][0]['table_id'] = 2
        with self.assertRaisesRegex(ValueError, 'Protected'):
            run_review(s,w,f,digest(s))

    def test_changed_source_digest(self):
        s,w,f = self.setup_case()
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            run_review(s,w,f,'0'*64)

    def test_upstream_math_promotion_rejected(self):
        s,w,f = self.setup_case()
        s['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'authorize'):
            run_review(s,w,f,digest(s))

    def test_upstream_incorrect_count_rejected(self):
        s,w,f = self.setup_case()
        s['counts']['structurally_complete_unverified'] = 0
        with self.assertRaisesRegex(ValueError, 'complete count'):
            run_review(s,w,f,digest(s))

    def test_upstream_bad_hand_rejected(self):
        s,w,f = self.setup_case()
        s['hands'][0]['human_entry']['hero_cards'][0] = '2c'
        with self.assertRaisesRegex(ValueError, 'Duplicate visible'):
            run_review(s,w,f,digest(s))

    def test_file_round_trip_and_no_overwrite(self):
        s = source()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            draft, worksheet, completed, output = (p/n for n in ('draft.json', 'worksheet.json', 'filled.json', 'result.json'))
            draft.write_text(json.dumps(s), encoding='utf-8')
            w = export_template(draft, worksheet)
            self.assertEqual(w['counts']['hands'], 1)
            f = filled_scenario(w)
            completed.write_text(json.dumps(f), encoding='utf-8')
            r = export_math(draft, worksheet, completed, output)
            self.assertEqual(r['counts']['hypothetical'], 1)
            self.assertEqual(json.loads(output.read_text()), r)
            with self.assertRaises(FileExistsError):
                export_math(draft, worksheet, completed, output)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); real=p/'real'; real.write_text(json.dumps(source()))
            link=p/'link'; link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                export_template(link,p/'output')

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); raw=p/'draft'; raw.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                export_template(raw,p/'output')

    def test_changed_input_during_validation(self):
        s=source()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); draft=p/'draft'; out=p/'out'; draft.write_text(json.dumps(s))
            real=make_worksheet
            def change(obj, sha):
                draft.write_text('{}')
                return real(obj,sha)
            with patch('offline_job_hand_math_review.make_worksheet', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    export_template(draft,out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
