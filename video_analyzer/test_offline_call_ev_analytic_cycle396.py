"""Analytic regression for conditional offline call EV, with no video dependency."""
import unittest
from offline_call_ev_bounds import call_ev_bounds


class AnalyticCallEV(unittest.TestCase):
    def test_constant_equity_linear_payoff(self):
        for pot in (0, 25, 100):
            for cost in (1, 20, 50):
                for q in (0, .25, .5, .75, 1):
                    with self.subTest(pot=pot, cost=cost, q=q):
                        result = call_ev_bounds(pot_before_call=pot, call_cost=cost,
                                                equity_interval=(q, q))
                        self.assertAlmostEqual(result['call_ev_interval'][0], q * (pot + cost) - cost)
                        self.assertEqual(result['call_ev_interval'][0], result['call_ev_interval'][1])
                        self.assertFalse(result['gto_solution'])
                        self.assertFalse(result['hand_error_verified'])

    def test_rake_reduces_payoff_and_increases_threshold(self):
        plain = call_ev_bounds(pot_before_call=100, call_cost=25, equity_interval=(.4, .6))
        raked = call_ev_bounds(pot_before_call=100, call_cost=25, equity_interval=(.4, .6),
                               rake_fraction=.1, rake_cap=5)
        self.assertEqual(raked['rake'], 5)
        self.assertGreater(raked['break_even_equity'], plain['break_even_equity'])
        for a, b in zip(plain['call_ev_interval'], raked['call_ev_interval']):
            self.assertGreater(a, b)

    def test_zero_distributable_pot(self):
        r = call_ev_bounds(pot_before_call=0, call_cost=10, equity_interval=(0, 1),
                           rake_fraction=1, rake_cap=10)
        self.assertIsNone(r['break_even_equity'])
        self.assertEqual(r['call_ev_interval'], [-10., -10.])

    def test_reject_nonfinite_and_bool(self):
        for invalid in (float('nan'), float('inf'), -1, True, '0.5'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                call_ev_bounds(pot_before_call=100, call_cost=10, equity_interval=(invalid, .8))

    def test_interval_width_is_equity_width_times_distributable_pot(self):
        r = call_ev_bounds(pot_before_call=80, call_cost=20, equity_interval=(.2, .7),
                           rake_fraction=.1, rake_cap=4)
        self.assertAlmostEqual(r['call_ev_interval'][1] - r['call_ev_interval'][0], .5 * 96)


if __name__ == '__main__':
    unittest.main()
