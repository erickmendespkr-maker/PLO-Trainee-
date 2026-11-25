import unittest
from plo5_cfr_restricted import optimize, certificate

# AA always wins, QQ always loses, against KK; bluff has twice the mass.
PAIRS=[(0,0,1/3,1.,2.),(1,0,2/3,0.,-1.)]

class RestrictedTests(unittest.TestCase):
    def test_polar(self):
        for alg in ('vanilla','cfr_plus'):
            r=optimize(PAIRS,2,1,iterations=20000,algorithm=alg,target=.01)
            self.assertTrue(r['target_reached']);self.assertLessEqual(r['gap'],.01)
            self.assertAlmostEqual(r['value'],.5,delta=.01)
            self.assertAlmostEqual(r['hero_bet_probabilities'][1],.25,delta=.03)
            self.assertAlmostEqual(r['opponent_call_probabilities'][0],.5,delta=.03)
    def test_exact_equilibrium(self):
        r=certificate(PAIRS,[1.,.25],[.5],2,1)
        self.assertAlmostEqual(r['gap'],0.);self.assertAlmostEqual(r['value'],.5)
    def test_bad_policy(self):
        self.assertGreater(certificate(PAIRS,[1.,1.],[0.],2,1)['gap'],.1)
    def test_budget(self):
        for kwargs in ({'iterations':0},{'algorithm':'unknown'},{'target':float('nan')},{'check_every':0}):
            with self.assertRaises(ValueError):optimize(PAIRS,2,1,**kwargs)
    def test_pair_checks(self):
        for pairs in ([PAIRS[0]],PAIRS+[PAIRS[0]],[(2,0,1.,1.,2.)],[(0,0,1.,.25,1.)]):
            with self.assertRaises(ValueError):optimize(pairs,2,1)
    def test_determinism_and_unreached(self):
        r=optimize(PAIRS,2,1,iterations=1,target=0)
        self.assertFalse(r['target_reached']);self.assertFalse(r['gto_solution'])
        self.assertEqual(r,optimize(PAIRS,2,1,iterations=1,target=0))
    def test_tie(self):
        r=optimize([(0,0,1.,.5,.5)],1,1)
        self.assertTrue(r['target_reached']);self.assertLessEqual(r['gap'],.01)

if __name__=='__main__':unittest.main()
