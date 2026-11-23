"""Regression tests for conditional Monte Carlo share summaries (synthetic only)."""
import math
import unittest
from .offline_monte_carlo_equity_summary import summarize_showdown_shares, to_call_scenario
from .offline_call_range_sensitivity import evaluate_call_scenarios


class MonteCarloEquitySummaryTests(unittest.TestCase):
    def test_balanced_binary_shares(self):
        s = summarize_showdown_shares([0.0, 1.0] * 50, seed=17, range_assumption="uniform hypothetical")
        self.assertEqual(s["equity"], 0.5)
        self.assertLess(s["equity_ci"][0], 0.5)
        self.assertGreater(s["equity_ci"][1], 0.5)
        self.assertEqual(s["samples"], 100)
        self.assertFalse(s["range_uncertainty_included"])

    def test_split_pot_share(self):
        s = summarize_showdown_shares([0.0, 0.5, 1.0] * 20, seed=2, range_assumption="hypothetical three-way")
        self.assertAlmostEqual(s["equity"], 0.5)
        self.assertEqual(s["status"], "APPROXIMATE_CI")

    def test_all_wins_are_not_certainty(self):
        s = summarize_showdown_shares([1.0] * 50, seed=3, range_assumption="hypothetical")
        self.assertEqual(s["equity_ci"], [0.0, 1.0])
        self.assertEqual(s["status"], "INSUFFICIENT_PRECISION")
        with self.assertRaises(ValueError):
            to_call_scenario("all wins", s)

    def test_reject_invalid_samples(self):
        for samples in ([0.0] * 29, [0.0] * 29 + [float("nan")], [0.0] * 29 + [True], [0.0] * 29 + [1.1]):
            with self.subTest(samples=samples[-1]):
                with self.assertRaises(ValueError):
                    summarize_showdown_shares(samples, seed=1, range_assumption="hypothetical")

    def test_reject_invalid_seed_and_range(self):
        with self.assertRaises(ValueError):
            summarize_showdown_shares([0, 1] * 20, seed=True, range_assumption="x")
        with self.assertRaises(ValueError):
            summarize_showdown_shares([0, 1] * 20, seed=1, range_assumption=" ")

    def test_conditional_ev_adapter(self):
        s = summarize_showdown_shares([0.0, 1.0] * 50, seed=7, range_assumption="fixed opponent range")
        scenario = to_call_scenario("baseline", s)
        result = evaluate_call_scenarios(100, 50, [scenario])
        self.assertEqual(result["strategic_verdict"], "NOT_ESTABLISHED")
        self.assertFalse(result["scenario_envelope_is_confidence_interval"])
        self.assertAlmostEqual(result["scenarios"][0]["call_ev_chips"], 25.0)


if __name__ == "__main__":
    unittest.main()
