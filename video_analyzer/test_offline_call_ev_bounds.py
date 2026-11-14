"""Synthetic tests for offline hypothetical call EV."""
import unittest
from offline_call_ev_bounds import call_ev_bounds

class CallEVTests(unittest.TestCase):
    def test_zero_equity(self):
        self.assertEqual(call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[0,0])["call_ev_interval"],[-50,-50])
    def test_full_equity(self):
        self.assertEqual(call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[1,1])["call_ev_interval"],[100,100])
    def test_breakeven(self):
        r=call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[1/3,1/3])
        self.assertAlmostEqual(r["call_ev_interval"][0],0)
        self.assertAlmostEqual(r["break_even_equity"],1/3)
    def test_interval(self):
        self.assertEqual(call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[.2,.6])["call_ev_interval"],[-20,40])
    def test_capped_rake(self):
        r=call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[1,1],rake_fraction=.1,rake_cap=5)
        self.assertEqual(r["rake"],5)
        self.assertEqual(r["call_ev_interval"],[95,95])
    def test_zero_cap_means_no_rake(self):
        self.assertEqual(call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[1,1],rake_fraction=.1)["rake"],0)
    def test_tie_equity(self):
        self.assertEqual(call_ev_bounds(pot_before_call=50,call_cost=50,equity_interval=[.5,.5])["call_ev_interval"],[0,0])
    def test_invalid(self):
        base=dict(pot_before_call=100,call_cost=50,equity_interval=[.2,.8])
        for change in ({"pot_before_call":float("nan")},{"call_cost":0},{"equity_interval":[.8,.2]},
                       {"equity_interval":[0,1.1]},{"equity_interval":[True,1]},
                       {"rake_fraction":1.1},{"rake_cap":-1},{"equity_interval":[]},
                       {"call_cost":float("inf")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                call_ev_bounds(**(base | change))
    def test_unverified(self):
        r=call_ev_bounds(pot_before_call=100,call_cost=50,equity_interval=[.3,.7])
        self.assertFalse(r["hand_error_verified"])
        self.assertFalse(r["gto_solution"])
        self.assertFalse(r["ranges_verified"])

if __name__ == "__main__":
    unittest.main()
