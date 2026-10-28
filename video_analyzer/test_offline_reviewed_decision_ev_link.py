"""Offline synthetic tests for reviewed-action -> hypothetical EV provenance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_four_table_action_timeline_audit as audit
import offline_omaha_conditional_ev as ev
import offline_reviewed_decision_ev_link as link
from test_offline_four_table_action_timeline_audit import report as hand_report
from test_offline_omaha_conditional_ev import fixture as ev_fixture


def write(path, obj):
    path.write_text(json.dumps(obj, allow_nan=False) + '\n', encoding='utf-8')


class DecisionLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.hands = self.root / 'hands.json'
        self.audit = self.root / 'audit.json'
        self.scenario = self.root / 'scenario.json'
        self.ev = self.root / 'ev.json'
        self.approval = self.root / 'approval.json'
        self.out = self.root / 'linked.json'
        self.video = self.root / 'video.mp4'
        self.video.write_bytes(b'synthetic video marker, not a poker recording')
        self.hands_data = hand_report()
        self.hands_data['recording_sha256'] = audit.sha(self.video)
        self.hands_data['hands'][0]['observations'][4]['value'] = 'call'
        self.scenario_data = copy.deepcopy(ev_fixture())
        for key in ('call_scenario', 'raise_called_scenario'):
            self.scenario_data[key]['hero_hole'] = ['As', 'Ks', 'Qs', 'Js', 'Ts']
            self.scenario_data[key]['known_board'] = ['2c', '3d', '4h']
        self.scenario_data['pot_before_decision'] = '120.00'
        self.prepare()

    def prepare(self):
        self.audit.unlink(missing_ok=True)
        self.ev.unlink(missing_ok=True)
        write(self.hands, self.hands_data)
        audit.build(self.hands, self.audit)
        write(self.scenario, self.scenario_data)
        ev.process(self.scenario, self.ev)
        self.approval_data = {
            'schema_version': 1,
            'source_hand_candidates_sha256': audit.sha(self.hands),
            'source_action_audit_sha256': audit.sha(self.audit),
            'source_ev_scenario_sha256': audit.sha(self.scenario),
            'source_ev_report_sha256': audit.sha(self.ev),
            'reviewer_confirmed_offline': True,
            'hand_id': 'hand1', 'table_id': 1,
            'decision_id': self.scenario_data['decision_id'],
            'hero_observation_index': 0, 'board_observation_index': 2,
            'pot_observation_index': 3, 'action_observation_index': 4,
            'observed_action_label': 'call',
            'heads_up_terminal_showdown_is_hypothesis': True,
            'pot_units_reviewed': True,
            'call_cost_and_raise_are_hypotheses': True,
            'reviewer_note': 'Synthetic example; no authenticated video evidence',
        }
        write(self.approval, self.approval_data)

    def run_link(self, *, video=False):
        return link.link(self.hands, self.audit, self.scenario, self.ev,
                         self.approval, self.out,
                         recording_path=self.video if video else None)

    def reject(self):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.run_link()
        self.assertFalse(self.out.exists())

    def approve(self, **updates):
        self.approval_data.update(updates)
        write(self.approval, self.approval_data)

    def test_valid_plo5(self):
        result = self.run_link()
        self.assertEqual(result['game_type'], 'PLO5')
        self.assertEqual(result['observed_action_label'], 'call')
        self.assertTrue(result['recomputed_ev_and_audit_from_supplied_inputs'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['decision_quality_verified'])
        self.assertEqual(json.loads(self.out.read_text()), result)

    def test_valid_plo6(self):
        self.hands_data['hands'][0]['declared_game_type'] = 'PLO6'
        self.hands_data['hands'][0]['observations'][0]['value'] += ' 9s'
        for key in ('call_scenario', 'raise_called_scenario'):
            self.scenario_data[key]['game_type'] = 'PLO6'
            self.scenario_data[key]['hero_hole'].append('9s')
            self.scenario_data[key]['explicit_villain_hands'] = [['7c', '7d', '8h', 'Th', 'Tc', 'Jd']]
        self.prepare()
        self.assertEqual(self.run_link()['game_type'], 'PLO6')

    def test_four_tables_select_fourth_only(self):
        template = copy.deepcopy(self.hands_data['hands'][0])
        selected = [template['observations'][i] for i in (0, 2, 3, 4)]
        hands = []
        for table in range(1, 5):
            h = copy.deepcopy(template)
            h['table_id'] = table
            h['hand_id'] = f'hand{table}'
            h['observations'] = copy.deepcopy(selected)
            for j, o in enumerate(h['observations']):
                o['reviewed_candidate_index'] = (table-1)*4+j
            h['missing_observed_fields'] = ['bet', 'stack']
            hands.append(h)
        self.hands_data['hands'] = hands
        self.prepare()
        self.approve(hand_id='hand4', table_id=4,
                     hero_observation_index=12, board_observation_index=13,
                     pot_observation_index=14, action_observation_index=15)
        r = self.run_link()
        self.assertEqual((r['table_id'], r['hand_id']), (4, 'hand4'))
        self.assertFalse(r['automatic_clip_selection_authorized'])

    def test_recording_verified_by_hash_only(self):
        r = self.run_link(video=True)
        self.assertTrue(r['recording_hash_checked_in_this_run'])
        self.assertFalse(r['video_evidence_independently_verified'])

    def test_wrong_recording_rejected(self):
        self.video.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.run_link(video=True)

    def test_no_existing_output_overwrite(self):
        self.out.write_text('do not overwrite')
        with self.assertRaises(ValueError): self.run_link()
        self.assertEqual(self.out.read_text(), 'do not overwrite')

    def test_no_source_overwrite(self):
        with self.assertRaises(ValueError):
            link.link(self.hands, self.audit, self.scenario, self.ev,
                      self.approval, self.ev)

    def test_missing_approval(self):
        self.approval.unlink()
        self.reject()

    def test_unreviewed_approval(self):
        self.approve(reviewer_confirmed_offline=False)
        self.reject()

    def test_hypothesis_flag_false(self):
        self.approve(heads_up_terminal_showdown_is_hypothesis=False)
        self.reject()

    def test_pot_units_not_reviewed(self):
        self.approve(pot_units_reviewed=False)
        self.reject()

    def test_call_cost_not_hypothetical(self):
        self.approve(call_cost_and_raise_are_hypotheses=False)
        self.reject()

    def test_cross_table_rejected(self):
        self.approve(table_id=2)
        self.reject()

    def test_wrong_hand_rejected(self):
        self.approve(hand_id='other')
        self.reject()

    def test_wrong_action_index(self):
        self.approve(action_observation_index=8)
        self.reject()

    def test_reused_index(self):
        self.approve(action_observation_index=3)
        self.reject()

    def test_boolean_index(self):
        self.approve(action_observation_index=True)
        self.reject()

    def test_action_label_mismatch(self):
        self.approve(observed_action_label='raise')
        self.reject()

    def test_unsupported_check_action(self):
        self.approve(observed_action_label='check')
        self.reject()

    def test_changed_approval_hash(self):
        self.approve(source_ev_report_sha256='f'*64)
        self.reject()

    def test_extra_approval_field(self):
        self.approve(ready_for_auto_selection=True)
        self.reject()

    def test_duplicate_json_key(self):
        self.approval.write_text('{"schema_version":1,"schema_version":1}')
        self.reject()

    def test_nan_json_rejected(self):
        self.approval.write_text('{"schema_version":NaN}')
        self.reject()

    def test_symlink_approval_rejected(self):
        other = self.root / 'real.json'
        self.approval.rename(other)
        self.approval.symlink_to(other)
        self.reject()

    def test_tampered_ev_report_even_if_hash_updated(self):
        r = json.loads(self.ev.read_text())
        r['ev_call'] = '9999.99'
        write(self.ev, r)
        self.approve(source_ev_report_sha256=audit.sha(self.ev))
        self.reject()

    def test_tampered_action_audit_even_if_hash_updated(self):
        r = json.loads(self.audit.read_text())
        r['hands'][0]['observed_action_labels'][1]['actor'] = 'hero'
        write(self.audit, r)
        self.approve(source_action_audit_sha256=audit.sha(self.audit))
        self.reject()

    def test_wrong_pot_even_with_fresh_ev_report(self):
        self.scenario_data['pot_before_decision'] = '121.00'
        self.prepare()
        self.reject()

    def test_wrong_board_even_with_fresh_ev_report(self):
        for key in ('call_scenario', 'raise_called_scenario'):
            self.scenario_data[key]['known_board'] = ['2c', '3d', '5h']
        self.prepare()
        self.reject()

    def test_wrong_hero_even_with_fresh_ev_report(self):
        for key in ('call_scenario', 'raise_called_scenario'):
            self.scenario_data[key]['hero_hole'][0] = 'Ah'
        self.prepare()
        self.reject()

    def test_stale_pot_snapshot(self):
        self.hands_data['hands'][0]['observations'][3]['pts_seconds'] = 0.5
        self.hands_data['hands'][0]['observations'].sort(
            key=lambda o: (o['pts_seconds'], o['reviewed_candidate_index']))
        self.prepare()
        self.reject()

    def test_ambiguous_action_timestamp(self):
        self.hands_data['hands'][0]['observations'][1]['pts_seconds'] = 6.0
        self.hands_data['hands'][0]['observations'].sort(
            key=lambda o: (o['pts_seconds'], o['reviewed_candidate_index']))
        self.prepare()
        self.reject()

    def test_newer_board_supersedes_approved_snapshot(self):
        self.hands_data['hands'][0]['observations'][5]['pts_seconds'] = 5.5
        self.hands_data['hands'][0]['observations'].sort(
            key=lambda o: (o['pts_seconds'], o['reviewed_candidate_index']))
        self.prepare()
        self.reject()

    def test_intervening_bet_invalidates_pot(self):
        self.hands_data['hands'][0]['observations'].append({
            'reviewed_candidate_index': 9, 'pts_seconds': 5.5,
            'field': 'bet', 'value': '20',
            'source_crop_sha256': 'a'*64,
            'source_crop_path': 'tables/extra.png', 'review_decision': 'correct'})
        self.hands_data['hands'][0]['observations'].sort(
            key=lambda o: (o['pts_seconds'], o['reviewed_candidate_index']))
        self.prepare()
        self.reject()

    def test_card_collision_rejected(self):
        self.hands_data['hands'][0]['observations'][0]['value'] = '2c Ks Qs Js Ts'
        self.prepare()
        self.reject()

    def test_missing_observed_pot(self):
        self.hands_data['hands'][0]['observations'] = [
            o for o in self.hands_data['hands'][0]['observations']
            if o['field'] != 'pot']
        self.prepare()
        self.reject()

    def test_nonexistent_decision_id(self):
        self.approve(decision_id='wrong-decision')
        self.reject()

    def test_no_auto_promotion_from_modified_hands(self):
        self.hands_data['ready_for_equity_or_ev'] = True
        write(self.hands, self.hands_data)
        self.approve(source_hand_candidates_sha256=audit.sha(self.hands))
        self.reject()

    def test_changed_source_ev_scenario(self):
        self.scenario_data['fold_probability'] = .8
        write(self.scenario, self.scenario_data)
        self.approve(source_ev_scenario_sha256=audit.sha(self.scenario))
        self.reject()


if __name__ == '__main__':
    unittest.main()
