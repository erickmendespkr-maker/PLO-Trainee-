"""Synthetic fail-closed contract tests; no real video or equity calculation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_mc_input_contract as mc


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.summary = {
            'schema_version': 1,
            'status': 'offline_hand_visual_summary_unverified_not_math_ready',
            'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
            'reviewer_claims_not_authenticated': True,
            'video_content_not_semantically_verified': True,
            'source_video_sha256_claim': 'a' * 64,
            'hand_count': 1,
            'hands': [{'hand_id': 'H1', 'table_id': 'T1', 'math_ready': False,
                       'eligible_for_equity': False, 'declared_fields': []}]
        }
        self.summary_path = self.root / 'summary.json'
        self.scenario_path = self.root / 'scenario.json'
        self.output_path = self.root / 'validated.json'
        self.write_summary()
        self.scenario = {
            'schema_version': 1, 'hand_id': 'H1', 'table_id': 'T1',
            'source_summary_sha256': mc.sha256(self.summary_path),
            'source_video_sha256_claim': 'a' * 64,
            'input_origin': 'independent_manual_transcription',
            'variant': 'PLO5', 'hero_cards': ['As', 'Kh', 'Qd', 'Jc', 'Ts'],
            'board_cards': ['2c', '3d', '4h'],
            'opponents': [{'range_name': 'manual_range_1', 'combos': [
                {'cards': ['5s', '6s', '7s', '8s', '9s'], 'weight': 1.0}]}],
            'pot_before_call': 100, 'to_call': 25, 'effective_stack': 300,
            'seed': 123, 'simulations': 10000,
            'assumptions': 'Independent manual cards and a hypothetical opponent range.',
            'future_action_model': 'showdown_equity_only'
        }
        self.write_scenario()

    def write_summary(self):
        self.summary_path.write_text(json.dumps(self.summary))

    def write_scenario(self):
        self.scenario_path.write_text(json.dumps(self.scenario))

    def build(self):
        return mc.build(self.summary, self.scenario, mc.sha256(self.summary_path))

    def test_valid_candidate_is_not_equity(self):
        result = self.build()
        self.assertEqual(result['street'], 'flop')
        self.assertFalse(result['equity_calculated'])
        self.assertFalse(result['ev_calculated'])
        self.assertFalse(result['automatic_ocr_math_authorization'])

    def test_plo6_river(self):
        self.scenario['variant'] = 'PLO6'
        self.scenario['hero_cards'].append('2s')
        self.scenario['board_cards'].extend(['5c', '6d'])
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['7c','8d','9h','Tc','Jd','Qc']
        self.assertEqual(self.build()['street'], 'river')

    def test_turn(self):
        self.scenario['board_cards'].append('5c')
        self.assertEqual(self.build()['street'], 'turn')

    def test_no_automatic_ocr_promotion(self):
        self.scenario['input_origin'] = 'ocr_review'
        with self.assertRaisesRegex(ValueError, 'cannot be promoted'): self.build()

    def test_wrong_summary_hash(self):
        self.scenario['source_summary_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'provenance'): self.build()

    def test_wrong_video_hash(self):
        self.scenario['source_video_sha256_claim'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'provenance'): self.build()

    def test_wrong_hand(self):
        self.scenario['hand_id'] = 'H2'
        with self.assertRaisesRegex(ValueError, 'uniquely linked'): self.build()

    def test_math_ready_forgery(self):
        self.summary['eligible_for_equity'] = True
        with self.assertRaisesRegex(ValueError, 'unverified summary'): self.build()

    def test_missing_hero(self):
        self.scenario['hero_cards'].pop()
        with self.assertRaisesRegex(ValueError, 'wrong number'): self.build()

    def test_hero_board_collision(self):
        self.scenario['board_cards'][0] = 'As'
        with self.assertRaisesRegex(ValueError, 'collision'): self.build()

    def test_duplicate_hero(self):
        self.scenario['hero_cards'][1] = 'As'
        with self.assertRaisesRegex(ValueError, 'duplicate'): self.build()

    def test_invalid_card(self):
        self.scenario['hero_cards'][0] = '1s'
        with self.assertRaisesRegex(ValueError, 'invalid card'): self.build()

    def test_invalid_board_count(self):
        self.scenario['board_cards'] = ['2c', '3d']
        with self.assertRaisesRegex(ValueError, 'board must'): self.build()

    def test_opponent_collides_known(self):
        self.scenario['opponents'][0]['combos'][0]['cards'][0] = 'As'
        with self.assertRaisesRegex(ValueError, 'collides'): self.build()

    def test_duplicate_unordered_combo(self):
        a = self.scenario['opponents'][0]['combos'][0]
        self.scenario['opponents'][0]['combos'].append({'cards': list(reversed(a['cards'])), 'weight': 2})
        with self.assertRaisesRegex(ValueError, 'duplicate unordered'): self.build()

    def test_no_joint_assignment(self):
        opponent = copy.deepcopy(self.scenario['opponents'][0])
        opponent['range_name'] = 'range_2'
        self.scenario['opponents'].append(opponent)
        with self.assertRaisesRegex(ValueError, 'no feasible disjoint'): self.build()

    def test_two_disjoint_opponents(self):
        opponent = copy.deepcopy(self.scenario['opponents'][0])
        opponent['range_name'] = 'range_2'
        opponent['combos'][0]['cards'] = ['5c','6c','7c','8c','9c']
        self.scenario['opponents'].append(opponent)
        self.assertEqual(len(self.build()['opponents']), 2)

    def test_four_opponents_rejected(self):
        self.scenario['opponents'] *= 4
        with self.assertRaisesRegex(ValueError, '1-3'): self.build()

    def test_zero_weight(self):
        self.scenario['opponents'][0]['combos'][0]['weight'] = 0
        with self.assertRaisesRegex(ValueError, 'weight'): self.build()

    def test_nonfinite_weight(self):
        self.scenario['opponents'][0]['combos'][0]['weight'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'weight'): self.build()

    def test_boolean_seed(self):
        self.scenario['seed'] = True
        with self.assertRaisesRegex(ValueError, 'seed'): self.build()

    def test_simulation_limit(self):
        self.scenario['simulations'] = 999
        with self.assertRaisesRegex(ValueError, 'simulation count'): self.build()

    def test_to_call_exceeds_stack(self):
        self.scenario['to_call'] = 301
        with self.assertRaisesRegex(ValueError, 'exceeds'): self.build()

    def test_negative_pot(self):
        self.scenario['pot_before_call'] = -1
        with self.assertRaisesRegex(ValueError, 'invalid amount'): self.build()

    def test_unsupported_future_model(self):
        self.scenario['future_action_model'] = 'raise_ev'
        with self.assertRaisesRegex(ValueError, 'unsupported future'): self.build()

    def test_empty_assumptions(self):
        self.scenario['assumptions'] = 'no'
        with self.assertRaisesRegex(ValueError, 'assumptions'): self.build()

    def test_unknown_extra_key(self):
        self.scenario['eligible_for_equity'] = True
        with self.assertRaisesRegex(ValueError, 'schema'): self.build()

    def test_cli_and_no_overwrite(self):
        args = [str(self.summary_path), str(self.scenario_path), str(self.output_path)]
        self.assertEqual(mc.main(args), 0)
        self.assertFalse(json.loads(self.output_path.read_text())['equity_calculated'])
        with self.assertRaisesRegex(ValueError, 'new and distinct'): mc.main(args)

    def test_duplicate_json_key(self):
        self.scenario_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            mc.main([str(self.summary_path), str(self.scenario_path), str(self.output_path)])

    def test_nan_json(self):
        self.scenario_path.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            mc.main([str(self.summary_path), str(self.scenario_path), str(self.output_path)])

    def test_input_file_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'new and distinct'):
            mc.main([str(self.summary_path), str(self.scenario_path), str(self.summary_path)])


if __name__ == '__main__':
    unittest.main()
