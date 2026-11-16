"""Regression: explicit EV bounds remain conditional, never a GTO verdict."""
import unittest
from offline_call_ev_bounds import call_ev_bounds


class ConditionalCallEVRegression(unittest.TestCase):
    def test_break_even_no_rake(self):
        r = call_ev_bounds(pot_before_call=100, call_cost=50, equity_interval=(1/3, 1/3))
        self.assertAlmostEqual(r["call_ev_interval"][0], 0)
        self.assertAlmostEqual(r["break_even_equity"], 1/3)

    def test_interval_monotonicity(self):
        r = call_ev_bounds(pot_before_call=100, call_cost=50, equity_interval=(.2, .5))
        self.assertAlmostEqual(r["call_ev_interval"][0], -20)
        self.assertAlmostEqual(r["call_ev_interval"][1], 25)
        self.assertFalse(r["hand_error_verified"])
        self.assertFalse(r["gto_solution"])

    def test_extremes(self):
        r = call_ev_bounds(pot_before_call=100, call_cost=50, equity_interval=(0, 1))
        self.assertEqual(r["call_ev_interval"], [-50.0, 100.0])

    def test_capped_rake(self):
        r = call_ev_bounds(pot_before_call=100, call_cost=50, equity_interval=(.5, .5),
                           rake_fraction=.1, rake_cap=5)
        self.assertEqual(r["rake"], 5)
        self.assertAlmostEqual(r["call_ev_interval"][0], 22.5)

    def test_invalid_inputs_fail_closed(self):
        cases = [
            {"pot_before_call": -1, "call_cost": 50, "equity_interval": (.2, .3)},
            {"pot_before_call": 100, "call_cost": 0, "equity_interval": (.2, .3)},
            {"pot_before_call": 100, "call_cost": 50, "equity_interval": (.7, .2)},
            {"pot_before_call": 100, "call_cost": 50, "equity_interval": (.2, 1.2)},
            {"pot_before_call": 100, "call_cost": 50, "equity_interval": (float("nan"), .3)},
            {"pot_before_call": True, "call_cost": 50, "equity_interval": (.2, .3)},
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                call_ev_bounds(**args)


if __name__ == "__main__":
    unittest.main()
