"""Offline synthetic regression tests: no real poker data or live integration."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_action_bet_timeline import inspect, run

HEX = 'a' * 64


def observation(index, field, value, t, review='confirmed'):
    return {'proposal_index': index, 'timestamp_seconds': t, 'value': value, 'review': review}


def document():
    entries = {
        'hero_cards': [observation(0, 'hero_cards', 'As Ks Qs Js Ts', 0.5)],
        'board': [observation(1, 'board', '2h 3h 4h', 3),
                  observation(2, 'board', '2h 3h 4h 5h', 9),
                  observation(3, 'board', '2h 3h 4h 5h 6h', 13)],
        'pot': [observation(4, 'pot', '50.00', 3.1), observation(5, 'pot', '75.00', 9.1)],
        'bet': [observation(6, 'bet', '25.00', 4.1)],
        'action': [observation(7, 'action', 'call', 4.0),
                   observation(8, 'action', 'check', 10.0)],
    }
    return {'schema_version': 1, 'analysis_status': 'offline_reviewed_hand_drafts_only',
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'source_reviewed_report_sha256': HEX,
            'source_boundaries_sha256': HEX, 'source_roi_ocr_report_sha256': HEX,
            'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                       'start_seconds': 0, 'end_seconds': 20,
                       'boundary_origin': 'manual_unverified',
                       'status': 'draft_requires_human_reconstruction',
                       'ready_for_equity_or_ev': False,
                       'reviewed_fields': entries,
                       'observation_indices': list(range(9)), 'unresolved_indices': []}]}


class ActionTimelineTests(unittest.TestCase):
    def setUp(self):
        self.d = document()

    def result(self):
        return inspect(self.d)

    def warnings(self):
        return self.result()['hands'][0]['warnings']

    def test_good_timeline_is_evidence_only(self):
        result = self.result()
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['hands_reconstructed'])
        self.assertEqual(result['hands'][0]['warnings'], [])
        self.assertEqual(len(result['hands'][0]['events']), 9)

    def test_action_has_no_actor_or_legality(self):
        action = next(e for e in self.result()['hands'][0]['events'] if e['value'] == 'call')
        self.assertEqual(action['nearby_bet_proposal_indices'], [6])
        self.assertFalse(action['actor_identified'])
        self.assertFalse(action['action_legality_verified'])
        self.assertEqual(action['board_phase_evidence'], 'flop_board_observed')

    def test_no_board_is_not_assumed_preflop(self):
        self.d['hands'][0]['reviewed_fields'].pop('board')
        self.d['hands'][0]['observation_indices'] = [0, 4, 5, 6, 7, 8]
        self.assertIn('no_visible_board', self.warnings())
        action = next(e for e in self.result()['hands'][0]['events'] if e['field'] == 'action')
        self.assertEqual(action['board_phase_evidence'], 'street_unknown')

    def test_pot_decrease(self):
        self.d['hands'][0]['reviewed_fields']['pot'][1]['value'] = '20.00'
        self.assertIn('pot_decreased_between_observations', self.warnings())

    def test_same_time_conflicting_pot(self):
        self.d['hands'][0]['reviewed_fields']['pot'][1]['timestamp_seconds'] = 3.1
        self.assertIn('conflicting_simultaneous_pot_values', self.warnings())

    def test_board_regression(self):
        self.d['hands'][0]['reviewed_fields']['board'][2]['value'] = '2h 3h 4h'
        self.assertIn('board_regressed', self.warnings())

    def test_board_changed_nonprefix(self):
        self.d['hands'][0]['reviewed_fields']['board'][1]['value'] = '2h 3h 4h 7s'
        self.assertIn('board_changed_nonprefix', self.warnings())

    def test_unresolved_propagation(self):
        h = self.d['hands'][0]
        h['unresolved_indices'] = [9]
        h['observation_indices'].append(9)
        self.assertIn('unresolved_ocr', self.warnings())

    def test_missing_action(self):
        h = self.d['hands'][0]
        h['reviewed_fields'].pop('action')
        h['observation_indices'] = list(range(7))
        self.assertIn('no_visible_action', self.warnings())

    def test_action_without_bet_is_warning_only(self):
        h = self.d['hands'][0]
        h['reviewed_fields'].pop('bet')
        h['observation_indices'].remove(6)
        self.assertIn('action_without_nearby_bet_ocr', self.warnings())

    def test_bet_near_two_actions(self):
        h = self.d['hands'][0]
        h['reviewed_fields']['action'][1]['timestamp_seconds'] = 4.5
        self.assertIn('bet_observation_near_multiple_actions', self.warnings())

    def test_simultaneous_actions(self):
        self.d['hands'][0]['reviewed_fields']['action'][1]['timestamp_seconds'] = 4
        self.assertIn('conflicting_simultaneous_actions', self.warnings())

    def test_partial_board(self):
        self.d['hands'][0]['reviewed_fields']['board'][0]['value'] = '2h 3h'
        self.assertIn('partial_board_snapshot', self.warnings())

    def test_reject_false_ev_ready(self):
        self.d['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError): self.result()

    def test_reject_duplicate_indices(self):
        self.d['hands'][0]['observation_indices'].append(8)
        with self.assertRaises(ValueError): self.result()

    def test_reject_missing_index(self):
        self.d['hands'][0]['observation_indices'].remove(8)
        with self.assertRaises(ValueError): self.result()

    def test_reject_invalid_card(self):
        self.d['hands'][0]['reviewed_fields']['board'][0]['value'] = 'As As 4h'
        with self.assertRaises(ValueError): self.result()

    def test_reject_invalid_money(self):
        self.d['hands'][0]['reviewed_fields']['pot'][0]['value'] = '-1'
        with self.assertRaises(ValueError): self.result()

    def test_reject_out_of_hand_pts(self):
        self.d['hands'][0]['reviewed_fields']['action'][0]['timestamp_seconds'] = 21
        with self.assertRaises(ValueError): self.result()

    def test_reject_nan(self):
        self.d['hands'][0]['reviewed_fields']['action'][0]['timestamp_seconds'] = float('nan')
        with self.assertRaises(ValueError): self.result()

    def test_reject_duplicate_hand_id(self):
        self.d['hands'].append(copy.deepcopy(self.d['hands'][0]))
        with self.assertRaises(ValueError): self.result()

    def test_reject_overlap_same_table(self):
        h = copy.deepcopy(self.d['hands'][0])
        h['hand_id'] = 'H2'
        h['observation_indices'] = []
        h['reviewed_fields'] = {}
        h['start_seconds'] = 10
        h['end_seconds'] = 15
        self.d['hands'].append(h)
        with self.assertRaises(ValueError): self.result()

    def test_other_table_may_overlap(self):
        h = copy.deepcopy(self.d['hands'][0])
        h['hand_id'] = 'H2'
        h['table_id'] = 4
        h['variant'] = 'PLO6'
        h['observation_indices'] = []
        h['reviewed_fields'] = {}
        self.d['hands'].append(h)
        self.assertEqual(len(self.result()['hands']), 2)

    def test_reject_unresolved_duplicate(self):
        h = self.d['hands'][0]
        h['observation_indices'].append(9)
        h['unresolved_indices'] = [9, 9]
        with self.assertRaises(ValueError): self.result()

    def test_reject_wrong_hero_count(self):
        self.d['hands'][0]['variant'] = 'PLO6'
        with self.assertRaises(ValueError): self.result()

    def test_cli_sha_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'input.json'
            out = Path(td) / 'output.json'
            raw = json.dumps(self.d).encode()
            src.write_bytes(raw)
            result = run(src, out)
            self.assertEqual(result['source_hand_drafts_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(json.loads(out.read_text()), result)
            with self.assertRaises(ValueError): run(src, out)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / 'input.json', Path(td) / 'output.json'
            src.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, 'duplicate'): run(src, out)
            self.assertFalse(out.exists())

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / 'input.json', Path(td) / 'output.json'
            src.write_text('{"x":NaN}')
            with self.assertRaises(ValueError): run(src, out)
            self.assertFalse(out.exists())

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src, link, out = Path(td) / 'input.json', Path(td) / 'link.json', Path(td) / 'out.json'
            src.write_text(json.dumps(self.d))
            link.symlink_to(src)
            with self.assertRaises(ValueError): run(link, out)

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src, target, out = Path(td) / 'input.json', Path(td) / 'target.json', Path(td) / 'out.json'
            src.write_text(json.dumps(self.d))
            target.write_text('sentinel')
            out.symlink_to(target)
            with self.assertRaises(ValueError): run(src, out)
            self.assertEqual(target.read_text(), 'sentinel')


if __name__ == '__main__':
    unittest.main()
