"""Synthetic mathematical invariants and offline CLI tests (no real video)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_mc_equity as mc
import offline_mc_input_contract as contract
from test_offline_mc_input_contract import ContractTests


class EquityTests(unittest.TestCase):
    build = ContractTests.build
    write_summary = ContractTests.write_summary
    write_scenario = ContractTests.write_scenario
    def setUp(self):
        ContractTests.setUp(self)
        self.scenario['hero_cards'] = ['As','Ks','9c','8d','7h']
        self.scenario['board_cards'] = ['Qs','Js','Ts','2c','3d']
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['2h','4d','5c','6h','7d']
        self.scenario['simulations'] = 1000
        self.write_scenario()

    def run_equity(self):
        return mc.compute(self.build())

    def test_royal_flush_win(self):
        r = self.run_equity()
        self.assertEqual(r['equity_fraction'], 1.0)
        self.assertEqual((r['hero_win_count'], r['hero_tie_count'], r['hero_loss_count']), (1000,0,0))
        self.assertEqual(r['confidence_interval_95_approx'], [1.0,1.0])
        self.assertFalse(r['ev_calculated'])

    def test_loss(self):
        self.scenario['hero_cards'], self.scenario['opponents'][0]['combos'][0]['cards'] = (self.scenario['opponents'][0]['combos'][0]['cards'], self.scenario['hero_cards'])
        self.assertEqual(self.run_equity()['equity_fraction'], 0.0)

    def test_split_pot(self):
        self.scenario['hero_cards'] = ['As','Ks','9c','8d','7h']
        self.scenario['board_cards'] = ['Qd','Jd','Td','2s','3s']
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['Ah','Kh','6c','5d','4h']
        r = self.run_equity()
        self.assertEqual(r['equity_fraction'], 0.5)
        self.assertEqual(r['hero_tie_count'], 1000)

    def test_turn_runout_deterministic(self):
        self.scenario['board_cards'].pop()
        a = self.run_equity()
        b = self.run_equity()
        self.assertEqual(a, b)
        self.assertEqual(a['hero_win_count']+a['hero_tie_count']+a['hero_loss_count'], 1000)
        self.assertTrue(0 <= a['confidence_interval_95_approx'][0] <= a['equity_fraction'] <= a['confidence_interval_95_approx'][1] <= 1)

    def test_flop_runout_deterministic(self):
        self.scenario['board_cards'] = self.scenario['board_cards'][:3]
        a = self.run_equity()
        self.assertEqual(a, self.run_equity())

    def test_plo6(self):
        self.scenario['variant'] = 'PLO6'
        self.scenario['hero_cards'].append('6s')
        self.scenario['opponents'][0]['combos'][0]['cards'].append('8h')
        self.assertEqual(self.run_equity()['equity_fraction'], 1.0)

    def test_joint_weight_conditional(self):
        self.scenario['opponents'][0]['combos'].append({'cards':['2h','4d','5c','6h','8h'],'weight':3})
        self.scenario['opponents'].append({'range_name':'second','combos':[{'cards':['2h','4c','5d','6c','9d'],'weight':2}, {'cards':['2d','4h','5h','6d','9h'],'weight':1}]})
        sampler, count = mc.joint_range_sampler(self.build())
        self.assertEqual(count, 2)  # only two disjoint joint assignments
        from random import Random
        rng = Random(42)
        for _ in range(100):
            hands = sampler(rng)
            self.assertFalse(set(hands[0]) & set(hands[1]))

    def test_three_way_tie_pot_share(self):
        self.scenario['board_cards'] = ['Qd','Jd','Td','2s','3s']
        self.scenario['opponents'][0]['combos'][0]['cards'] = ['Ah','Kh','6c','5d','4h']
        self.scenario['opponents'].append({'range_name':'third','combos':[
            {'cards':['Ac','Kc','6d','5h','4c'],'weight':1}]})
        result = self.run_equity()
        self.assertAlmostEqual(result['equity_fraction'], 1/3, places=12)
        self.assertEqual(result['hero_tie_count'], 1000)

    def test_range_weights_influence_conditional_equity(self):
        self.scenario['hero_cards'] = ['Ah','Kh','9c','8d','7h']
        self.scenario['opponents'][0]['combos'] = [
            {'cards':['As','Ks','2h','4d','5c'],'weight':1},
            {'cards':['2d','4c','5d','6h','7d'],'weight':3}]
        result = self.run_equity()
        self.assertAlmostEqual(result['equity_fraction'], 0.75, delta=0.07)
        self.assertEqual(result['joint_feasible_range_assignments'], 2)

    def test_runtime_cap_is_explicit(self):
        self.scenario['simulations'] = mc.MAX_TRIALS + 1
        with self.assertRaisesRegex(ValueError, 'simulation count'):
            self.run_equity()

    def test_input_unchanged_after_execution(self):
        before = (contract.sha256(self.summary_path), contract.sha256(self.scenario_path))
        self.run_equity()
        self.assertEqual(before, (contract.sha256(self.summary_path), contract.sha256(self.scenario_path)))

    def test_five_card_hand_ranking(self):
        rank = mc.five_card_rank
        self.assertGreater(rank(tuple('As Ks Qs Js Ts'.split())), rank(tuple('9h 9s 9d 9c Ah'.split())))
        self.assertGreater(rank(tuple('As 2h 3c 4d 5s'.split())), rank(tuple('Ah Ad Kh Qd 2c'.split())))
        self.assertLess(rank(tuple('As 2h 3c 4d 5s'.split())), rank(tuple('2s 3h 4c 5d 6s'.split())))
        self.assertGreater(rank(tuple('Kh Kd Ks Qh Qd'.split())), rank(tuple('Ah Jh 9h 7h 2h'.split())))

    def test_omaha_exactly_two_hole(self):
        hero = ['As','Ks','Qs','Js','2d']
        board = ['2s','5s','8s','3c','4d']
        # Four spades in hand cannot form a royal flush: only two hole cards count.
        self.assertLess(mc.omaha_rank(hero, board)[0], 8)
        with self.assertRaises(ValueError): mc.omaha_rank(hero, board[:4])

    def test_no_ev_or_ocr_authorization(self):
        r = self.run_equity()
        self.assertIsNone(r['fold_call_raise_ev'])
        self.assertFalse(r['automatic_ocr_math_authorization'])
        self.assertIn('not_range_uncertainty', r['confidence_method'])

    def test_invalid_validated_status(self):
        v = self.build()
        v['status'] = 'ocr_promoted'
        with self.assertRaisesRegex(ValueError, 'not independently validated'): mc.compute(v)

    def test_cli_creates_new_file_and_rejects_overwrite(self):
        args = [str(self.summary_path), str(self.scenario_path), str(self.output_path)]
        self.assertEqual(mc.main(args), 0)
        result = json.loads(self.output_path.read_text())
        self.assertEqual(result['equity_fraction'], 1.0)
        self.assertEqual(result['source_scenario_sha256'], contract.sha256(self.scenario_path))
        with self.assertRaisesRegex(ValueError, 'new and distinct'): mc.main(args)

    def test_cli_rejects_ocr_origin(self):
        self.scenario['input_origin'] = 'ocr_review'
        self.write_scenario()
        with self.assertRaisesRegex(ValueError, 'cannot be promoted'):
            mc.main([str(self.summary_path), str(self.scenario_path), str(self.output_path)])
        self.assertFalse(self.output_path.exists())

    def test_cli_rejects_changed_summary(self):
        self.summary['source_video_sha256_claim'] = 'b'*64
        self.write_summary()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            mc.main([str(self.summary_path), str(self.scenario_path), str(self.output_path)])


if __name__ == '__main__':
    unittest.main()
