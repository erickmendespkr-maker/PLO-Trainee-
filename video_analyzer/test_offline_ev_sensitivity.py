import copy
import unittest
from offline_ev_sensitivity import evaluate_call_scenarios


def cases():
    return [{'range_id':'wide','equity':.30,'equity_ci':[.29,.31],'iterations':10000,'seed':42},
            {'range_id':'tight','equity':.20,'equity_ci':[.19,.21],'iterations':10000,'seed':43}]

class ScenarioTests(unittest.TestCase):
    def test_analytic_payoffs(self):
        out=evaluate_call_scenarios(150,50,cases())
        self.assertAlmostEqual(out['break_even_equity'], .25)
        self.assertAlmostEqual(out['scenarios'][0]['ev_call_bb'],10)
        self.assertAlmostEqual(out['scenarios'][1]['ev_call_bb'],-10)
        self.assertEqual(out['ev_envelope_bb'],[-12.,12.])
        self.assertTrue(out['range_sensitive'])
        self.assertFalse(out['gto_solution'])
    def test_all_positive(self):
        c=cases();c[1]['equity']=.4;c[1]['equity_ci']=[.39,.41]
        self.assertFalse(evaluate_call_scenarios(150,50,c)['range_sensitive'])
    def test_all_negative(self):
        c=cases();c[0]['equity']=.1;c[0]['equity_ci']=[.09,.11]
        self.assertFalse(evaluate_call_scenarios(150,50,c)['range_sensitive'])
    def test_boundary_uncertainty(self):
        c=cases();c[0]['equity']=.25;c[0]['equity_ci']=[.24,.26]
        self.assertEqual(evaluate_call_scenarios(150,50,c)['scenarios'][0]['conditional_label'],'uncertain_or_break_even')
    def test_nonfinite(self):
        for v in (float('nan'),float('inf'),True,-1):
            with self.subTest(v=v), self.assertRaises(ValueError):evaluate_call_scenarios(v,50,cases())
    def test_bad_interval(self):
        c=cases();c[0]['equity_ci']=[.31,.32]
        with self.assertRaises(ValueError):evaluate_call_scenarios(150,50,c)
    def test_duplicate_range(self):
        c=cases();c[1]['range_id']='wide'
        with self.assertRaises(ValueError):evaluate_call_scenarios(150,50,c)
    def test_bad_metadata(self):
        for key,val in [('seed',True),('iterations',0),('iterations',2.5)]:
            c=cases();c[0][key]=val
            with self.subTest(key=key), self.assertRaises(ValueError):evaluate_call_scenarios(150,50,c)
    def test_no_input_mutation(self):
        c=cases();orig=copy.deepcopy(c);evaluate_call_scenarios(150,50,c);self.assertEqual(c,orig)
    def test_no_verdict(self):
        o=evaluate_call_scenarios(150,50,cases())
        self.assertFalse(o['strategic_error_established']);self.assertFalse(o['automatic_clip_selection_authorized'])
    def test_reject_one_scenario(self):
        with self.assertRaises(ValueError):evaluate_call_scenarios(150,50,cases()[:1])
    def test_reject_boolean_equity(self):
        c=cases();c[0]['equity']=True
        with self.assertRaises(ValueError):evaluate_call_scenarios(150,50,c)

if __name__=='__main__':unittest.main()
