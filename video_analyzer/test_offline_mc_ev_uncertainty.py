import unittest
from offline_mc_ev_uncertainty import conditional_mc_call_ev

class MonteCarloEVTests(unittest.TestCase):
    def test_equity_and_ev(self):
        v = conditional_mc_call_ev(100, 50, {'range': [1, 0, .5]})
        self.assertAlmostEqual(v['scenarios']['range']['equity_estimate'], .5)
        self.assertAlmostEqual(v['scenarios']['range']['ev_estimate'], 25)
    def test_rake(self):
        self.assertAlmostEqual(conditional_mc_call_ev(100, 50, {'a':[1]}, 10)['scenarios']['a']['ev_estimate'],90)
    def test_zero_one_limits(self):
        v = conditional_mc_call_ev(100, 50, {'a':[0]*100, 'b':[1]*100})
        self.assertEqual(v['scenarios']['a']['equity_lower'], 0)
        self.assertEqual(v['scenarios']['b']['equity_upper'], 1)
    def test_more_samples_tighter(self):
        a = conditional_mc_call_ev(100, 50, {'a':[.5]*10})
        b = conditional_mc_call_ev(100, 50, {'a':[.5]*1000})
        self.assertGreater(a['scenarios']['a']['equity_upper']-a['scenarios']['a']['equity_lower'], b['scenarios']['a']['equity_upper']-b['scenarios']['a']['equity_lower'])
    def test_signal_positive(self):
        self.assertEqual(conditional_mc_call_ev(100, 10, {'a':[1]*1000})['conditional_signal'],'positive_across_scenarios')
    def test_signal_negative(self):
        self.assertEqual(conditional_mc_call_ev(100, 50, {'a':[0]*1000})['conditional_signal'],'negative_across_scenarios')
    def test_uncertain(self):
        self.assertEqual(conditional_mc_call_ev(100, 50, {'a':[0,1]})['conditional_signal'],'uncertain')
    def test_reject_invalid_samples(self):
        for samples in ([], [float('nan')], [-.1], [1.1], [True], ['.5']):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                conditional_mc_call_ev(100,50,{'a':samples})
    def test_reject_invalid_params(self):
        for args in ((-1,50,0,.95),(100,0,0,.95),(100,50,151,.95),(100,50,0,1),(100,50,0,float('nan'))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                p,c,r,conf=args
                conditional_mc_call_ev(p,c,{'a':[.5]},r,conf)
    def test_reject_empty_scenarios(self):
        with self.assertRaises(ValueError): conditional_mc_call_ev(100,50,{})
    def test_explicit_limits(self):
        v=conditional_mc_call_ev(100,50,{'a':[.5]})
        self.assertFalse(v['gto_solution'])
        self.assertFalse(v['strategic_verdict_allowed'])
        self.assertFalse(v['range_model_uncertainty_included'])

if __name__ == '__main__': unittest.main()
