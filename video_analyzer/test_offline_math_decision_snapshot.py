import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from offline_math_decision_snapshot import build, run


class DecisionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.review = {
            'schema_version': 1,
            'status': 'offline_human_reviewed_evidence_not_math_authorized',
            'automatic_ocr_math_authorization': False,
            'confidence_calibrated': False,
            'variant': 'PLO5',
            'hands': [{'table_id': 't1', 'hand_id': 'h1',
                       'start_seconds': 0, 'end_seconds': 100,
                       'review_flags': [], 'card_evidence_consistent': True,
                       'automatic_math_authorization': False,
                       'events': [
                           self.event(1, 'preflop', 'hero_cards', ['AS','KD','QC','JH','TS']),
                           self.event(20, 'flop', 'board', ['2C','3D','4H']),
                           self.event(40, 'turn', 'board', ['2C','3D','4H','5S']),
                           self.event(60, 'river', 'board', ['2C','3D','4H','5S','6C']),
                       ]}]
        }
        self.assumptions = {
            'schema_version': 1, 'table_id': 't1', 'hand_id': 'h1',
            'source_review_sha256': 'a'*64, 'reviewer_attestation': True,
            'range_source': 'Manually assumed range for test only',
            'villain_combos': [{'cards': ['7C','8D','9H','TC','JS'], 'weight': 1.0}],
            'pot_before_call': 100, 'to_call': 20, 'seed': 42, 'trials': 500,
            'model': 'heads_up_call_all_in_no_future_betting_no_rake',
            'decision_timestamp_seconds': 25, 'decision_street': 'flop'
        }

    @staticmethod
    def event(t, street, kind, value, decision='confirm'):
        return {'timestamp_seconds': t, 'street': street, 'kind': kind,
                'decision': decision, 'reviewed_value': value}

    def build(self):
        return build(self.review, self.assumptions, 'a'*64, 'b'*64)

    def test_flop_does_not_leak_turn_river(self):
        result = self.build()
        self.assertEqual(result['board'], ['2c', '3d', '4h'])
        self.assertEqual(result['decision_street'], 'flop')
        self.assertNotIn('5s', result['board'])
        self.assertNotIn('6c', result['board'])
        self.assertNotIn('equity', result)
        self.assertNotIn('ev', result)

    def test_preflop_snapshot(self):
        self.assumptions.update(decision_timestamp_seconds=5, decision_street='preflop')
        self.assertEqual(self.build()['board'], [])

    def test_turn_snapshot(self):
        self.assumptions.update(decision_timestamp_seconds=45, decision_street='turn')
        self.assertEqual(len(self.build()['board']), 4)

    def test_river_snapshot(self):
        self.assumptions.update(decision_timestamp_seconds=70, decision_street='river')
        self.assertEqual(len(self.build()['board']), 5)

    def test_plo6(self):
        self.review['variant'] = 'PLO6'
        self.review['hands'][0]['events'][0]['reviewed_value'].append('9S')
        self.assumptions['villain_combos'][0]['cards'].append('8C')
        self.assertEqual(len(self.build()['hero_cards']), 6)

    def test_duplicate_case_normalization(self):
        self.review['hands'][0]['events'][0]['reviewed_value'][-1] = 'As'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.build()

    def test_future_card_overlap_is_not_known_yet(self):
        # 5S appears on the turn, after a flop decision; it is a legal
        # *hypothetical* opponent card at the earlier timestamp.
        self.assumptions['villain_combos'][0]['cards'][0] = '5S'
        self.assertEqual(self.build()['villain_combos'][0]['cards'][0], '5s')

    def test_visible_card_overlap_is_blocked(self):
        self.assumptions['villain_combos'][0]['cards'][0] = '2C'
        with self.assertRaises(ValueError): self.build()

    def test_missing_hero_at_decision(self):
        self.assumptions.update(decision_timestamp_seconds=0, decision_street='preflop')
        with self.assertRaisesRegex(ValueError, 'hero cards not known'):
            self.build()

    def test_missing_board_at_decision(self):
        self.assumptions.update(decision_timestamp_seconds=19, decision_street='flop')
        with self.assertRaisesRegex(ValueError, 'board not fully observed'):
            self.build()

    def test_future_street_same_timestamp(self):
        self.review['hands'][0]['events'][2]['timestamp_seconds'] = 20
        with self.assertRaisesRegex(ValueError, 'future street'):
            self.build()

    def test_missing_event_timestamp(self):
        del self.review['hands'][0]['events'][0]['timestamp_seconds']
        with self.assertRaisesRegex(ValueError, 'missing timestamp'):
            self.build()

    def test_missing_event_street(self):
        del self.review['hands'][0]['events'][0]['street']
        with self.assertRaisesRegex(ValueError, 'missing timestamp'):
            self.build()

    def test_reverse_time(self):
        self.review['hands'][0]['events'][2]['timestamp_seconds'] = 10
        with self.assertRaisesRegex(ValueError, 'chronological'):
            self.build()

    def test_reverse_street(self):
        self.review['hands'][0]['events'][2]['street'] = 'preflop'
        with self.assertRaisesRegex(ValueError, 'chronological'):
            self.build()

    def test_rejected_flop_is_blocked(self):
        self.review['hands'][0]['events'][1]['decision'] = 'reject'
        with self.assertRaisesRegex(ValueError, 'unreviewed'):
            self.build()

    def test_rejected_future_river_does_not_affect_flop(self):
        self.review['hands'][0]['events'][3]['decision'] = 'reject'
        self.assertEqual(len(self.build()['board']), 3)

    def test_conflicting_hero_before_decision(self):
        self.review['hands'][0]['events'].insert(1,
            self.event(2, 'preflop', 'hero_cards', ['AC','KD','QC','JH','TS']))
        with self.assertRaisesRegex(ValueError, 'conflicting hero'):
            self.build()

    def test_out_of_hand(self):
        self.assumptions['decision_timestamp_seconds'] = 101
        with self.assertRaisesRegex(ValueError, 'outside hand'):
            self.build()

    def test_nan_time(self):
        self.assumptions['decision_timestamp_seconds'] = float('nan')
        with self.assertRaises(ValueError): self.build()

    def test_bool_time(self):
        self.assumptions['decision_timestamp_seconds'] = True
        with self.assertRaises(ValueError): self.build()

    def test_unsupported_model(self):
        self.assumptions['model'] = 'multiway_raise'
        with self.assertRaises(ValueError): self.build()

    def test_duplicate_opponent_combo_after_case_normalization(self):
        self.assumptions['villain_combos'].append({
            'cards': ['7c','8d','9h','Tc','Js'], 'weight': 2})
        with self.assertRaises(ValueError): self.build()

    def test_review_flags_block(self):
        self.review['hands'][0]['review_flags'] = ['conflict']
        with self.assertRaises(ValueError): self.build()

    def test_attestation_block(self):
        self.assumptions['reviewer_attestation'] = False
        with self.assertRaises(ValueError): self.build()

    def test_unknown_schema_key_block(self):
        self.assumptions['secret'] = 3
        with self.assertRaises(ValueError): self.build()

    def test_file_roundtrip_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = d/'review.json'
            a = d/'assumptions.json'
            out = d/'result.json'
            r.write_text(json.dumps(self.review))
            self.assumptions['source_review_sha256'] = hashlib.sha256(r.read_bytes()).hexdigest()
            a.write_text(json.dumps(self.assumptions))
            result = run(r, a, out)
            self.assertEqual(json.loads(out.read_text()), result)
            self.assertEqual(result['source_full_review_sha256'], hashlib.sha256(r.read_bytes()).hexdigest())
            self.assertEqual(result['source_full_assumptions_sha256'], hashlib.sha256(a.read_bytes()).hexdigest())
            with self.assertRaises(ValueError): run(r, a, out)

    def test_file_symlink_input_block(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = d/'review.json'
            a = d/'assumptions.json'
            link = d/'link.json'
            r.write_text(json.dumps(self.review))
            link.symlink_to(r)
            a.write_text(json.dumps(self.assumptions))
            with self.assertRaises(ValueError): run(link, a, d/'out.json')


if __name__ == '__main__':
    unittest.main()
