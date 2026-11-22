import unittest
from offline_ev_call_bounds import call_ev_bounds

class TestCallEVBounds(unittest.TestCase):
    def test_break_even(self):
        r = call_ev_bounds(pot_before=100, call_cost=50, equity_low=1/3, equity_high=1/3)
        self.assertAlmostEqual(r['ev_low_chips'], 0)
        self.assertAlmostEqual(r['break_even_equity'], 1/3)
    def test_win_lose(self):
        r = call_ev_bounds(pot_before=100, call_cost=50, equity_low=0, equity_high=1)
        self.assertEqual((r['ev_low_chips'], r['ev_high_chips']), (-50,100))
    def test_range_sensitive(self):
        r = call_ev_bounds(pot_before=100, call_cost=50, equity_low=.2, equity_high=.5)
        self.assertTrue(r['range_sensitive'])
    def test_robust_positive(self):
        r = call_ev_bounds(pot_before=100, call_cost=50, equity_low=.6, equity_high=.7)
        self.assertFalse(r['range_sensitive'])
        self.assertGreater(r['ev_low_chips'], 0)
    def test_invalid(self):
        cases = [(100,0,.2,.3),(10,20,.2,.3),(100,50,.9,.1),(100,50,-.1,.3),(100,50,.2,1.1),(float('nan'),50,.2,.3),(True,50,.2,.3)]
        for p,c,lo,hi in cases:
            with self.subTest(case=(p,c,lo,hi)), self.assertRaises(ValueError):
                call_ev_bounds(pot_before=p, call_cost=c, equity_low=lo, equity_high=hi)

if __name__ == '__main__': unittest.main()
