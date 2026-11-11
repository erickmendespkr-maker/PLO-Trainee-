"""Synthetic weighted-range tests, no real poker footage."""
import unittest
from offline_weighted_ranges import prepare, equity, exact_river
from offline_omaha_equity import exact
H=['Ac','Ad','Ah','As','2c']
V=['Kc','Kd','Kh','Ks','3c']
V2=['Qc','Qd','Qh','Qs','3d']
B=['4d','5d','6d','7d','8d']
class WeightedRangeTests(unittest.TestCase):
    def test_one_holding_river_matches_existing_exact(self):
        r=exact_river(H,B,[{'cards':V,'weight':3}]);self.assertEqual(r['equity'],exact(H,V,B)['equity'])
    def test_mc_river_single_holding(self):
        self.assertEqual(equity(H,B,[{'cards':V,'weight':1}],20,1)['equity'],exact(H,V,B)['equity'])
    def test_reproducible(self):
        x=[{'cards':V,'weight':3},{'cards':V2,'weight':1}]
        self.assertEqual(equity(H,B[:4],x,100,8),equity(H,B[:4],x,100,8))
    def test_blocked_weight(self):
        blocked=['Ac','Kc','Kh','Ks','3c']
        a,meta=prepare(H,B,[{'cards':V,'weight':1},{'cards':blocked,'weight':3}])
        self.assertEqual(len(a),1);self.assertEqual(meta['blocked_weight_fraction'],.75)
    def test_all_blocked(self):
        with self.assertRaises(ValueError):prepare(H,B,[{'cards':['Ac','Kc','Kh','Ks','3c'],'weight':1}])
    def test_duplicate_permutation(self):
        with self.assertRaises(ValueError):prepare(H,B,[{'cards':V,'weight':1},{'cards':V[::-1],'weight':1}])
    def test_negative_weight(self):
        with self.assertRaises(ValueError):prepare(H,B,[{'cards':V,'weight':-1}])
    def test_bool_weight(self):
        with self.assertRaises(ValueError):prepare(H,B,[{'cards':V,'weight':True}])
    def test_duplicate_hero(self):
        with self.assertRaises(ValueError):prepare(H[:4]+['Ac'],B,[{'cards':V,'weight':1}])
    def test_bad_board(self):
        with self.assertRaises(ValueError):prepare(H,B[:2],[{'cards':V,'weight':1}])
    def test_bad_seed(self):
        with self.assertRaises(ValueError):equity(H,B,[{'cards':V,'weight':1}],20,True)
    def test_river_only(self):
        with self.assertRaises(ValueError):exact_river(H,B[:4],[{'cards':V,'weight':1}])
    def test_plo6(self):
        h=H+['Tc'];v=V+['Jc'];r=equity(h,B[:4],[{'cards':v,'weight':1}],30,5)
        self.assertEqual(r['trials'],30)
    def test_no_range_confidence_claim(self):
        r=equity(H,B,[{'cards':V,'weight':1}],20,0)
        self.assertFalse(r['range_uncertainty_included_in_ci']);self.assertFalse(r['gto_solution'])
if __name__=='__main__':unittest.main()
