"""Synthetic PLO5/PLO6 tests; no private video or poker service."""
import unittest
from offline_omaha_equity import five_rank, omaha_rank, exact, monte_carlo, validate
H=['Ac','Ad','Ah','As','2c']
V=['Kc','Kd','Kh','Ks','3c']
B=['4d','5d','6d','7d','8d']
class OmahaTests(unittest.TestCase):
    def test_wheel(self): self.assertEqual(five_rank(['Ac','2d','3h','4s','5c']),(4,5))
    def test_royal(self): self.assertEqual(five_rank(['Tc','Jc','Qc','Kc','Ac']),(8,14))
    def test_quads(self): self.assertEqual(five_rank(['2c','2d','2h','2s','Ac'])[0],7)
    def test_fullhouse(self): self.assertEqual(five_rank(['2c','2d','2h','As','Ac'])[0],6)
    def test_two_hole_rule(self):
        h=['Ac','Kd','2d','3d','4h'];b=['Qc','Jc','Tc','9c','8c']
        self.assertNotEqual(omaha_rank(h,b)[0],8)
    def test_board_only_flush_not_valid(self):
        h=['2c','3d','4h','5s','6c'];b=['Ac','Kc','Qc','Jc','Tc']
        self.assertNotEqual(omaha_rank(h,b)[0],8)
    def test_exact_tie(self):
        h=['Ac','Kd','2h','3s','4c'];v=['Ad','Kc','2s','3h','4d'];b=['5c','6d','7h','8s','9c']
        r=exact(h,v,b);self.assertEqual(r['trials'],1);self.assertEqual(r['equity'],.5)
    def test_exact_repro(self): self.assertEqual(exact(H,V,B),exact(H,V,B))
    def test_mc_seed(self): self.assertEqual(monte_carlo(H,V,B,50,7),monte_carlo(H,V,B,50,7))
    def test_mc_exact_board(self): self.assertEqual(monte_carlo(H,V,B,30,1)['equity'],exact(H,V,B)['equity'])
    def test_ci_bounds(self):
        r=monte_carlo(H,V,B[:4],200,3)
        self.assertLessEqual(r['ci95_conservative'][0],r['equity'])
        self.assertGreaterEqual(r['ci95_conservative'][1],r['equity'])
    def test_duplicate(self):
        with self.assertRaises(ValueError): validate(H,V,['Ac','5d','6d'])
    def test_wrong_hole(self):
        with self.assertRaises(ValueError): validate(H[:4],V,B)
    def test_bool_seed(self):
        with self.assertRaises(ValueError): monte_carlo(H,V,B,10,True)
    def test_exact_cap(self):
        with self.assertRaises(ValueError): exact(H,V,[],100)
    def test_plo6(self):
        h=H+['Tc'];v=V+['Jc'];r=monte_carlo(h,v,B[:4],50,3)
        self.assertEqual(r['trials'],50)
if __name__=='__main__': unittest.main()
