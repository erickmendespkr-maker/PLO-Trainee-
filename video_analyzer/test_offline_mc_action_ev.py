"""Synthetic offline EV model tests: chip accounting, boundaries, fail-closed provenance."""
import copy
import json
from pathlib import Path
import unittest

import offline_mc_action_ev as ev
import offline_mc_input_contract as contract
import offline_mc_equity as mc
from test_offline_mc_input_contract import ContractTests


class ActionEVTests(unittest.TestCase):
    build = ContractTests.build
    write_summary = ContractTests.write_summary
    write_scenario = ContractTests.write_scenario

    def setUp(self):
        ContractTests.setUp(self)
        self.scenario['hero_cards'] = ['As','Ks','9c','8d','7h']
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['2h','4d','5c','6h','7d']
        self.scenario['board_cards'] = ['Qs', 'Js', 'Ts', '2c', '3d']
        self.scenario['simulations'] = 1000
        self.write_scenario()
        self.actions_path = self.root / 'actions.json'
        self.ev_output = self.root / 'ev.json'
        self.actions = {
            'schema_version': 1,
            'source_scenario_sha256': contract.sha256(self.scenario_path),
            'model': ev.MODEL, 'rake': 0,
            'assumptions': 'All other players already committed; no further betting or rake.',
            'raise_model': None,
        }
        self.write_actions()

    def write_actions(self):
        self.actions_path.write_text(json.dumps(self.actions))

    def raise_model(self, total=75, fold=0.2, called=0.5):
        self.actions['raise_model'] = {
            'raise_total': total, 'fold_probability': fold,
            'called_equity_fraction': called, 'opponent_can_match_raise': True,
            'assumptions': 'Opponent can match full raise; fold probability and called equity are independently assumed.'}

    def run_ev(self):
        validated = self.build()
        equity = mc.compute(validated)
        return ev.calculate(validated, equity, self.actions, contract.sha256(self.scenario_path))

    def test_fold_zero_and_call_winning_equity(self):
        result = self.run_ev()
        self.assertEqual(result['equity_fraction'], 1.0)
        self.assertEqual(result['ev_fold_chips'], 0)
        self.assertEqual(result['ev_call_or_check_chips'], 100)
        self.assertEqual(result['ev_call_or_check_confidence_interval_95_approx_chips'], [100,100])
        self.assertIsNone(result['ev_raise_model'])

    def test_call_loss_is_negative_call(self):
        self.scenario['hero_cards'], self.scenario['opponents'][0]['combos'][0]['cards'] = (
            self.scenario['opponents'][0]['combos'][0]['cards'], self.scenario['hero_cards'])
        self.assertEqual(self.run_ev()['ev_call_or_check_chips'], -25)

    def test_call_split_expected_accounting(self):
        self.scenario['board_cards'] = ['Qd','Jd','Td','2s','3s']
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['Ah','Kh','6c','5d','4h']
        self.assertEqual(self.run_ev()['ev_call_or_check_chips'], 37.5)

    def test_check_when_to_call_zero(self):
        self.scenario['to_call'] = 0
        r = self.run_ev()
        self.assertEqual(r['call_action_label'], 'check')
        self.assertEqual(r['ev_call_or_check_chips'], 100)

    def test_raise_full_fold(self):
        self.raise_model(fold=1.0, called=0.0)
        self.assertEqual(self.run_ev()['ev_raise_model']['ev_chips'], 100)

    def test_raise_called_full_loss(self):
        self.raise_model(fold=0, called=0)
        self.assertEqual(self.run_ev()['ev_raise_model']['ev_chips'], -75)

    def test_raise_called_full_win(self):
        self.raise_model(fold=0, called=1)
        result = self.run_ev()['ev_raise_model']
        self.assertEqual(result['opponent_extra_call_chips'], 50)
        self.assertEqual(result['ev_chips'], 150)

    def test_raise_blended_expected(self):
        self.raise_model(fold=0.2, called=0.5)
        self.assertAlmostEqual(self.run_ev()['ev_raise_model']['ev_chips'], 50)

    def test_raise_no_confidence_interval(self):
        self.raise_model()
        result = self.run_ev()['ev_raise_model']
        self.assertIsNone(result['confidence_interval_95'])
        self.assertIn('manual assumptions', result['confidence_note'])

    def test_raise_equal_to_call_rejected(self):
        self.raise_model(total=25)
        with self.assertRaisesRegex(ValueError, 'raise_total'): self.run_ev()

    def test_raise_exceeds_stack_rejected(self):
        self.raise_model(total=301)
        with self.assertRaisesRegex(ValueError, 'raise_total'): self.run_ev()

    def test_raise_without_opponent_stack_assumption(self):
        self.raise_model()
        self.actions['raise_model']['opponent_can_match_raise'] = False
        with self.assertRaisesRegex(ValueError, 'stack coverage'): self.run_ev()

    def test_raise_multiway_rejected(self):
        self.raise_model()
        self.scenario['opponents'].append({'range_name':'second','combos':[
            {'cards':['2d','4c','5d','6c','9d'],'weight':1}]})
        with self.assertRaisesRegex(ValueError, 'heads-up'): self.run_ev()

    def test_invalid_probability_rejected(self):
        self.raise_model(fold=1.1)
        with self.assertRaisesRegex(ValueError, 'fold_probability'): self.run_ev()

    def test_nan_called_equity_rejected(self):
        self.raise_model(called=float('nan'))
        with self.assertRaisesRegex(ValueError, 'called_equity_fraction'): self.run_ev()

    def test_bool_probability_rejected(self):
        self.raise_model(fold=True)
        with self.assertRaisesRegex(ValueError, 'fold_probability'): self.run_ev()

    def test_wrong_model_rejected(self):
        self.actions['model'] = 'complex_future_betting'
        with self.assertRaisesRegex(ValueError, 'unsupported EV model'): self.run_ev()

    def test_nonzero_rake_rejected(self):
        self.actions['rake'] = 0.05
        with self.assertRaisesRegex(ValueError, 'rake'): self.run_ev()

    def test_extra_field_rejected(self):
        self.actions['force_approve'] = True
        with self.assertRaisesRegex(ValueError, 'schema'): self.run_ev()

    def test_missing_assumptions_rejected(self):
        self.actions['assumptions'] = ''
        with self.assertRaisesRegex(ValueError, 'assumptions'): self.run_ev()

    def test_ocr_origin_rejected(self):
        self.scenario['input_origin'] = 'ocr_review'
        with self.assertRaisesRegex(ValueError, 'cannot be promoted'): self.run_ev()

    def test_scenario_hash_mismatch_rejected(self):
        self.actions['source_scenario_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'provenance'): self.run_ev()

    def test_deterministic_result(self):
        self.assertEqual(self.run_ev(), self.run_ev())

    def test_plo6(self):
        self.scenario['variant'] = 'PLO6'
        self.scenario['hero_cards'].append('6s')
        self.scenario['opponents'][0]['combos'][0]['cards'].append('8h')
        self.assertEqual(self.run_ev()['variant'], 'PLO6')

    def test_cli_writes_and_rejects_overwrite(self):
        self.write_actions()
        args = [str(self.summary_path),str(self.scenario_path),str(self.actions_path),str(self.ev_output)]
        self.assertEqual(ev.main(args), 0)
        result = json.loads(self.ev_output.read_text())
        self.assertEqual(result['ev_call_or_check_chips'], 100)
        self.assertEqual(result['source_action_sha256'], contract.sha256(self.actions_path))
        self.assertFalse(result['automatic_ocr_math_authorization'])
        with self.assertRaisesRegex(ValueError, 'new and distinct'): ev.main(args)

    def test_cli_invalid_actions_does_not_write(self):
        self.actions['source_scenario_sha256'] = '0'*64
        self.write_actions()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            ev.main([str(self.summary_path),str(self.scenario_path),str(self.actions_path),str(self.ev_output)])
        self.assertFalse(self.ev_output.exists())

    def test_cli_duplicate_json_keys_rejected(self):
        self.actions_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            ev.main([str(self.summary_path),str(self.scenario_path),str(self.actions_path),str(self.ev_output)])
        self.assertFalse(self.ev_output.exists())

    def test_cli_refuses_same_output_as_input(self):
        with self.assertRaisesRegex(ValueError, 'new and distinct'):
            ev.main([str(self.summary_path),str(self.scenario_path),str(self.actions_path),str(self.actions_path)])


if __name__ == '__main__':
    unittest.main()
