import unittest
from offline_ev_bounds import call_ev_bounds

class TestCallEV(unittest.TestCase):
    def test_break_even(self):
        self.assertAlmostEqual(call_ev_bounds(100,50,{'a':1/3})['ev_min'],0)
    def test_range_sensitive(self):
        self.assertEqual(call_ev_bounds(100,50,{'tight':.2,'loose':.6})['decision_robust'],'range_sensitive')
    def test_call_robust(self):
        self.assertEqual(call_ev_bounds(100,50,{'a':.5,'b':.6})['decision_robust'],'call')
    def test_fold_robust(self):
        self.assertEqual(call_ev_bounds(100,50,{'a':.1,'b':.2})['decision_robust'],'fold')
    def test_rake(self):
        self.assertAlmostEqual(call_ev_bounds(100,50,{'a':.5},10)['ev_min'],20)
    def test_tie_share(self):
        self.assertAlmostEqual(call_ev_bounds(100,50,{'tie_share':.5})['ev_min'],25)
    def test_empty(self):
        with self.assertRaises(ValueError): call_ev_bounds(100,50,{})
    def test_nan(self):
        with self.assertRaises(ValueError): call_ev_bounds(100,50,{'a':float('nan')})
    def test_bool(self):
        with self.assertRaises(ValueError): call_ev_bounds(100,50,{'a':True})
    def test_negative(self):
        with self.assertRaises(ValueError): call_ev_bounds(-1,50,{'a':.5})
    def test_rake_too_large(self):
        with self.assertRaises(ValueError): call_ev_bounds(100,50,{'a':.5},151)
    def test_no_gto(self):
        self.assertFalse(call_ev_bounds(100,50,{'a':.5})['gto_solution'])
if __name__ == '__main__': unittest.main()
