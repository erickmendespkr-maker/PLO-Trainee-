import unittest
from offline_bounded_equity_scenarios import bounded_equity_scenario, to_call_scenario


class BoundedEquityScenarioTests(unittest.TestCase):
    def test_balanced_shares(self):
        s = bounded_equity_scenario("tight", [0, 1] * 1000, seed=17, range_assumption="fixed tight range")
        self.assertAlmostEqual(s["equity"], .5)
        self.assertLess(s["equity_ci"][0], .5)
        self.assertGreater(s["equity_ci"][1], .5)
        self.assertEqual(s["status"], "CONSERVATIVE_CI")
        self.assertEqual(to_call_scenario(s)["name"], "tight")

    def test_constant_shares_not_zero_width(self):
        s = bounded_equity_scenario("tie", [.5] * 2000, seed=0, range_assumption="fixed")
        self.assertLess(s["equity_ci"][0], .5)
        self.assertGreater(s["equity_ci"][1], .5)

    def test_small_sample_rejected_by_adapter(self):
        s = bounded_equity_scenario("small", [0] * 30, seed=1, range_assumption="fixed")
        self.assertEqual(s["status"], "INSUFFICIENT_PRECISION")
        with self.assertRaises(ValueError):
            to_call_scenario(s)

    def test_invalid_inputs(self):
        for shares in ([0] * 29, [float("nan")] * 30, [1.1] * 30):
            with self.assertRaises(ValueError):
                bounded_equity_scenario("x", shares, seed=1, range_assumption="fixed")
        with self.assertRaises(ValueError):
            bounded_equity_scenario("x", [0] * 100, seed=True, range_assumption="fixed")
        with self.assertRaises(ValueError):
            bounded_equity_scenario("x", [0] * 100, seed=1, range_assumption="")

    def test_tampered_summary_rejected(self):
        s = bounded_equity_scenario("x", [0, 1] * 1000, seed=1, range_assumption="fixed")
        s["equity_ci"] = [.6, .7]
        with self.assertRaises(ValueError):
            to_call_scenario(s)


if __name__ == "__main__":
    unittest.main()
