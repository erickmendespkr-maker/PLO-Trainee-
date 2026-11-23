"""Integration regression: bounded showdown shares -> conditional range EV.

Run: python -m unittest video_analyzer.test_offline_bounded_equity_ev_integration
No real footage, live poker integration, or proprietary solver data.
"""
import unittest

from .offline_bounded_equity_scenarios import bounded_equity_scenario, to_call_scenario
from .offline_call_range_sensitivity import evaluate_call_scenarios


class BoundedEquityEVIntegrationTests(unittest.TestCase):
    def test_positive_across_fixed_hypotheses(self):
        a = bounded_equity_scenario("wide", [1.0] * 800 + [0.0] * 200,
                                    seed=11, range_assumption="synthetic wide")
        b = bounded_equity_scenario("tight", [1.0] * 750 + [0.0] * 250,
                                    seed=12, range_assumption="synthetic tight")
        result = evaluate_call_scenarios(100, 20, [to_call_scenario(a), to_call_scenario(b)])
        self.assertEqual(result["classification"], "POSITIVE_IN_ALL_SUPPLIED_SCENARIOS")
        self.assertFalse(result["scenario_envelope_is_confidence_interval"])
        self.assertEqual(result["strategic_verdict"], "NOT_ESTABLISHED")

    def test_negative_across_fixed_hypotheses(self):
        a = bounded_equity_scenario("a", [1.0] * 100 + [0.0] * 900,
                                    seed=3, range_assumption="synthetic A")
        b = bounded_equity_scenario("b", [1.0] * 80 + [0.0] * 920,
                                    seed=4, range_assumption="synthetic B")
        result = evaluate_call_scenarios(100, 100, [to_call_scenario(a), to_call_scenario(b)])
        self.assertEqual(result["classification"], "NEGATIVE_IN_ALL_SUPPLIED_SCENARIOS")

    def test_opposing_ranges_are_sensitive(self):
        a = bounded_equity_scenario("a", [1.0] * 800 + [0.0] * 200,
                                    seed=3, range_assumption="synthetic A")
        b = bounded_equity_scenario("b", [1.0] * 200 + [0.0] * 800,
                                    seed=4, range_assumption="synthetic B")
        result = evaluate_call_scenarios(100, 50, [to_call_scenario(a), to_call_scenario(b)])
        self.assertEqual(result["classification"], "RANGE_OR_SAMPLING_SENSITIVE")
        self.assertFalse(result["range_probabilities_known"])

    def test_small_sample_precision_blocks_ev(self):
        a = bounded_equity_scenario("uncertain", [1.0] * 15 + [0.0] * 15,
                                    seed=2, range_assumption="synthetic")
        self.assertEqual(a["status"], "INSUFFICIENT_PRECISION")
        with self.assertRaises(ValueError):
            to_call_scenario(a)

    def test_split_pots_preserve_fractional_equity(self):
        a = bounded_equity_scenario("split", [0.5] * 1000,
                                    seed=9, range_assumption="synthetic always split")
        self.assertAlmostEqual(a["equity"], 0.5)
        self.assertLess(a["equity_ci"][0], 0.5)
        self.assertGreater(a["equity_ci"][1], 0.5)
        result = evaluate_call_scenarios(100, 50, [to_call_scenario(a)])
        self.assertAlmostEqual(result["scenarios"][0]["call_ev_chips"], 25.0)

    def test_reproducible_summary(self):
        shares = [0, 1, 0.5, 1] * 300
        x = bounded_equity_scenario("repeat", shares, seed=42, range_assumption="fixed")
        y = bounded_equity_scenario("repeat", shares, seed=42, range_assumption="fixed")
        self.assertEqual(x, y)
        self.assertEqual(x["samples"], 1200)
        self.assertFalse(x["gto_solution"])


if __name__ == "__main__":
    unittest.main()
