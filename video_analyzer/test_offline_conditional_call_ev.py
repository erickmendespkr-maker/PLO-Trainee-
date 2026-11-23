"""Deterministic regression tests for simplified conditional call EV."""
import math
import unittest
try:
    from .offline_conditional_call_ev import conditional_call_ev
except ImportError:
    from offline_conditional_call_ev import conditional_call_ev


class ConditionalCallEVTests(unittest.TestCase):
    def test_break_even(self):
        x = conditional_call_ev(100, 50, 1/3)
        self.assertAlmostEqual(x["call_ev_chips"], 0)
        self.assertAlmostEqual(x["break_even_equity"], 1/3)

    def test_certain_win_and_loss(self):
        self.assertEqual(conditional_call_ev(100, 50, 1)["call_ev_chips"], 100)
        self.assertEqual(conditional_call_ev(100, 50, 0)["call_ev_chips"], -50)

    def test_interval_monotonic(self):
        x = conditional_call_ev(100, 50, .4, equity_ci=(.3, .5))
        self.assertEqual(x["call_ev_interval_chips"], [-5.0, 25.0])
        self.assertFalse(x["range_uncertainty_included"])
        self.assertEqual(x["strategic_verdict"], "NOT_ESTABLISHED")

    def test_invalid_inputs(self):
        for args in [(-1, 5, .5), (10, 0, .5), (10, 5, 1.1),
                     (10, 5, float("nan")), (10, 5, True)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                conditional_call_ev(*args)

    def test_invalid_intervals(self):
        for ci in [(.6, .7), (-.1, .6), (.2, float("inf")), (.5, .4), [0]]:
            with self.subTest(ci=ci), self.assertRaises(ValueError):
                conditional_call_ev(100, 50, .5, equity_ci=ci)


if __name__ == "__main__":
    unittest.main()
