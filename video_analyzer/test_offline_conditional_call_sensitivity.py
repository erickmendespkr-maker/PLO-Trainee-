"""Synthetic tests; never claim source video reconstruction."""
import json
from pathlib import Path
import tempfile
import unittest
import offline_conditional_call_sensitivity as m

class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.s = {'schema_version':1,
                  'source_type':'manually_authored_hypothetical_not_video_verified',
                  'scenario_id':'example_1','pot_before_call_bb':150,'call_cost_bb':50,
                  'assumptions':{'heads_up':True,'showdown_after_call':True,'no_rake':True,
                     'no_side_pots':True,'no_future_betting':True,
                     'equity_includes_tie_fraction':True},
                  'ranges':[{'range_id':'wide','equity':.3,'equity_ci95':[.28,.32],
                             'equity_method':'external_independent_monte_carlo_hypothesis',
                             'iterations':10000,'seed':42},
                            {'range_id':'tight','equity':.2,'equity_ci95':[.18,.22],
                             'equity_method':'external_independent_monte_carlo_hypothesis',
                             'iterations':10000,'seed':43}]}
    def test_ev_and_pot_odds(self):
        r=m.compute(self.s)
        self.assertEqual(r['break_even_equity'],.25)
        self.assertEqual(r['range_results'][0]['ev_call_bb'],10)
        self.assertEqual(r['range_results'][1]['ev_call_bb'],-10)
        self.assertTrue(r['range_sensitive'])
        self.assertFalse(r['strategic_error_established'])
    def test_all_positive_but_not_gto(self):
        self.s['ranges'][1]['equity']=.4
        self.s['ranges'][1]['equity_ci95']=[.38,.42]
        r=m.compute(self.s)
        self.assertFalse(r['range_sensitive'])
        self.assertFalse(r['source_hand_reconstruction_verified'])
    def test_interval_crosses_break_even(self):
        self.s['ranges'][0]['equity_ci95']=[.24,.32]
        self.assertEqual(m.compute(self.s)['range_results'][0]['conditional_label'],
                         'uncertain_or_break_even')
    def test_exact_break_even(self):
        self.s['ranges'][0]['equity']=.25
        self.s['ranges'][0]['equity_ci95']=[.25,.25]
        self.assertEqual(m.compute(self.s)['range_results'][0]['ev_call_bb'],0)
    def test_no_free_call(self):
        self.s['call_cost_bb']=0
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_no_bool_money(self):
        self.s['pot_before_call_bb']=True
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_no_bad_confidence(self):
        self.s['ranges'][0]['equity_ci95']=[.35,.4]
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_no_duplicate_range(self):
        self.s['ranges'][1]['range_id']='wide'
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_no_gto_promotion(self):
        self.s['assumptions']['no_future_betting']=False
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_no_nan(self):
        self.s['ranges'][0]['equity']=float('nan')
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_requires_multiple_ranges(self):
        self.s['ranges']=self.s['ranges'][:1]
        with self.assertRaises(ValueError):m.compute(self.s)
    def test_output_and_no_overwrite(self):
        src=self.root/'scenario.json'
        src.write_text(json.dumps(self.s),'utf-8')
        out=self.root/'result.json'
        r=m.run(src,out)
        self.assertEqual(r['source_scenario_sha256'],m.sha(src))
        self.assertEqual(json.loads(out.read_text())['range_results'][0]['ev_call_bb'],10)
        with self.assertRaises(ValueError):m.run(src,out)
    def test_duplicate_json_keys(self):
        src=self.root/'scenario.json'
        src.write_text('{"a":1,"a":2}','utf-8')
        with self.assertRaises(ValueError):m.run(src,self.root/'out.json')
    def test_reject_hidden_unsupported_fields(self):
        self.s['claimed_gto']=True
        with self.assertRaises(ValueError):m.compute(self.s)

if __name__=='__main__':
    unittest.main(verbosity=2)
