"""Synthetic offline integration tests; no real-session or OCR claims."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_math_mc_bridge as bridge

def candidate(variant='PLO5'):
    n = 5 if variant == 'PLO5' else 6
    hero = ['As', 'Kd', 'Qc', 'Jh', 'Ts'] + (['9s'] if n == 6 else [])
    villain = ['7c', '8d', '9h', 'Tc', 'Js'] + (['6c'] if n == 6 else [])
    return {
        'schema_version': 1, 'status': 'timestamp_scoped_reviewed_math_candidate_not_computed',
        'variant': variant, 'table_id': 't1', 'hand_id': 'h1',
        'hero_cards': hero, 'board': ['2c', '3d', '4h'],
        'villain_combos': [{'cards': villain, 'weight': 1.0}],
        'pot_before_call': 100, 'to_call': 20, 'seed': 42, 'trials': 100,
        'model': 'heads_up_call_all_in_no_future_betting_no_rake',
        'range_source': 'Manually assumed range for synthetic test',
        'source_review_sha256': 'a'*64, 'source_assumptions_sha256': 'b'*64,
        'source_full_review_sha256': 'a'*64,
        'source_full_assumptions_sha256': 'b'*64,
        'automatic_ocr_math_authorization': False,
        'confidence_note': 'Human reviewed fields, hypothetical range not calibrated.',
        'decision_timestamp_seconds': 25, 'decision_street': 'flop',
        'decision_board_cards': 3,
    }


class BridgeTests(unittest.TestCase):
    def test_plo5_real_local_mc_execution(self):
        r = bridge.build(candidate(), 'a'*64)
        self.assertEqual(r['trials'], 100)
        self.assertEqual(r['wins']+r['ties']+r['losses'], 100)
        self.assertEqual(r['status'], bridge.STATUS)
        self.assertEqual(r['mc_engine'], 'offline_omaha_equity_mc.estimate')
        self.assertFalse(r['automatic_clip_selection_authorized'])

    def test_plo6_real_local_mc_execution(self):
        r = bridge.build(candidate('PLO6'), 'b'*64)
        self.assertEqual(r['variant'], 'PLO6')
        self.assertEqual(r['trials'], 100)
        self.assertTrue(r['mc_engine_rule_exact_two_hole_three_board'])

    def test_fixed_seed_determinism(self):
        c = candidate()
        self.assertEqual(bridge.build(c,'a'*64), bridge.build(c,'a'*64))

    def test_equity_and_ev_arithmetic(self):
        r = bridge.build(candidate(), 'a'*64)
        self.assertAlmostEqual(r['equity_estimate'], (r['wins']+r['ties']*.5)/100)
        self.assertAlmostEqual(r['ev_call_estimate'], r['equity_estimate']*120-20)
        self.assertEqual(r['break_even_equity'], 20/120)
        self.assertLessEqual(r['equity_95pct_hoeffding_interval'][0],r['equity_estimate'])
        self.assertGreaterEqual(r['equity_95pct_hoeffding_interval'][1],r['equity_estimate'])

    def test_preflop_supported_with_zero_board(self):
        c=candidate(); c['board']=[];c['decision_street']='preflop';c['decision_board_cards']=0
        r=bridge.build(c,'a'*64)
        self.assertEqual(r['decision_street'],'preflop')

    def test_river_certain_win_royal_flush(self):
        c=candidate();c['hero_cards']=['As','Ks','2c','3d','4c']
        c['board']=['Qs','Js','Ts','8d','7c'];c['decision_street']='river';c['decision_board_cards']=5
        c['villain_combos']=[{'cards':['2h','3h','4h','5h','6h'],'weight':1}]
        r=bridge.build(c,'a'*64)
        self.assertEqual((r['wins'],r['ties'],r['losses']),(100,0,0))
        self.assertEqual(r['equity_estimate'],1)

    def test_nonuniform_weights_blocked(self):
        c=candidate();c['villain_combos'].append({'cards':['2h','3h','4d','5c','6s'],'weight':2})
        with self.assertRaisesRegex(ValueError,'weighted'):
            bridge.scenario_from_candidate(c)

    def test_future_board_blocked(self):
        c=candidate();c['board'].append('5s')
        with self.assertRaisesRegex(ValueError,'board/street'):
            bridge.scenario_from_candidate(c)

    def test_duplicate_visible_cards_blocked(self):
        c=candidate();c['board'][0]=c['hero_cards'][0]
        with self.assertRaises(ValueError):bridge.scenario_from_candidate(c)

    def test_overlap_opponent_blocked(self):
        c=candidate();c['villain_combos'][0]['cards'][0]=c['hero_cards'][0]
        with self.assertRaisesRegex(ValueError,'overlap'):
            bridge.scenario_from_candidate(c)

    def test_duplicate_opponent_combo_blocked(self):
        c=candidate();c['villain_combos'].append({'cards':list(reversed(c['villain_combos'][0]['cards'])),'weight':1})
        with self.assertRaisesRegex(ValueError,'duplicate opponent'):
            bridge.scenario_from_candidate(c)

    def test_unreviewed_status_blocked(self):
        c=candidate();c['status']='raw_ocr'
        with self.assertRaises(ValueError):bridge.scenario_from_candidate(c)

    def test_ocr_authorization_blocked(self):
        c=candidate();c['automatic_ocr_math_authorization']=True
        with self.assertRaises(ValueError):bridge.scenario_from_candidate(c)

    def test_source_hash_mismatch_blocked(self):
        c=candidate();c['source_full_review_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'provenance'):
            bridge.scenario_from_candidate(c)

    def test_seed_and_trials_limits(self):
        for key,value in [('seed',2**32),('seed',True),('trials',10001),('trials',True),('trials',99)]:
            with self.subTest(key=key,value=value):
                c=candidate();c[key]=value
                with self.assertRaises(ValueError):bridge.scenario_from_candidate(c)

    def test_model_unsupported(self):
        c=candidate();c['model']='multiway_raise'
        with self.assertRaises(ValueError):bridge.scenario_from_candidate(c)

    def test_corrupted_engine_counts_blocked(self):
        c=candidate()
        with patch.object(bridge.mc,'estimate',return_value={'wins':100}):
            with self.assertRaisesRegex(ValueError,'engine result'):
                bridge.build(c,'a'*64)

    def test_json_io_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'candidate.json';out=Path(td)/'report.json'
            src.write_text(json.dumps(candidate()),encoding='utf-8')
            r=bridge.run(src,out)
            self.assertEqual(json.loads(out.read_text())['source_candidate_sha256'],hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertEqual(r['status'],bridge.STATUS)
            with self.assertRaises(ValueError):bridge.run(src,out)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'bad.json';out=Path(td)/'out.json'
            src.write_text('{"status":"x","status":"y"}')
            with self.assertRaisesRegex(ValueError,'duplicate JSON key'):bridge.run(src,out)
            self.assertFalse(out.exists())

    def test_input_mutation_during_simulation_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'candidate.json';out=Path(td)/'out.json'
            src.write_text(json.dumps(candidate()))
            orig=bridge.build
            def mutate(c,h):
                result=orig(c,h)
                src.write_text(src.read_text()+' ')
                return result
            with patch.object(bridge,'build',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'changed'):
                    bridge.run(src,out)
            self.assertFalse(out.exists())


if __name__ == '__main__':unittest.main()
