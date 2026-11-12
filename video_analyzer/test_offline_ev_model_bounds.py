import copy
import unittest
from offline_ev_model_bounds import evaluate


def scenarios(a=(.28,.32), b=(.18,.22)):
    return [{'range_id':'wide','equity_interval_conditional':list(a)},
            {'range_id':'tight','equity_interval_conditional':list(b)}]


class TestModelBounds(unittest.TestCase):
    def test_range_sensitive(self):
        r=evaluate(150,50,scenarios())
        self.assertEqual(r['break_even_equity'],.25)
        self.assertEqual(r['conditional_comparison'],'range_sensitive_or_uncertain')
        self.assertAlmostEqual(r['ev_call_scenario_envelope_bb'][0],-14)
        self.assertAlmostEqual(r['ev_call_scenario_envelope_bb'][1],14)
    def test_call_both(self):
        self.assertEqual(evaluate(150,50,scenarios((.3,.4),(.26,.29)))['conditional_comparison'],'call_under_all_supplied_ranges')
    def test_fold_both(self):
        self.assertEqual(evaluate(150,50,scenarios((.1,.2),(.15,.24)))['conditional_comparison'],'fold_under_all_supplied_ranges')
    def test_boundary_is_indeterminate(self):
        self.assertEqual(evaluate(150,50,scenarios((.25,.3),(.3,.4)))['conditional_comparison'],'range_sensitive_or_uncertain')
    def test_fold_baseline_zero(self):
        r=evaluate(0,50,scenarios((1,1),(0,0)))
        self.assertEqual(r['break_even_equity'],1)
        self.assertEqual(r['ev_call_scenario_envelope_bb'],[-50,0])
    def test_reject_bool_money(self):
        with self.assertRaises(ValueError):evaluate(True,50,scenarios())
    def test_reject_nan(self):
        with self.assertRaises(ValueError):evaluate(float('nan'),50,scenarios())
    def test_reject_infinite_equity(self):
        s=scenarios();s[0]['equity_interval_conditional'][0]=float('inf')
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_inverted(self):
        with self.assertRaises(ValueError):evaluate(150,50,scenarios((.4,.3)))
    def test_reject_duplicate_id(self):
        s=scenarios();s[1]['range_id']='wide'
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_injection(self):
        s=scenarios();s[0]['range_id']='wide\nfalse'
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_missing_field(self):
        s=scenarios();del s[0]['range_id']
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_extra_field(self):
        s=scenarios();s[0]['gto_solution']=True
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_bool_equity(self):
        s=scenarios();s[0]['equity_interval_conditional'][0]=True
        with self.assertRaises(ValueError):evaluate(150,50,s)
    def test_reject_one_scenario(self):
        with self.assertRaises(ValueError):evaluate(150,50,scenarios()[:1])
    def test_no_strategic_claims(self):
        r=evaluate(150,50,scenarios())
        self.assertFalse(r['gto_solution'])
        self.assertFalse(r['strategic_error_established'])
        self.assertFalse(r['source_hand_reconstruction_verified'])
        self.assertFalse(r['range_uncertainty_quantified'])


if __name__ == '__main__': unittest.main(verbosity=2)
