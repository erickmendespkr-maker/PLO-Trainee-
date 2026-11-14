import unittest
from video_analyzer.offline_equity_ev_uncertainty import equity_interval_from_shares, evaluate_sampled_call_scenarios

class UncertaintyTests(unittest.TestCase):
    def test_mean_and_bounds(self):
        r = equity_interval_from_shares(shares=[1, 0, .5, .5])
        self.assertEqual(r["equity_estimate"], .5)
        self.assertLessEqual(r["equity_interval"][0], .5)
        self.assertGreaterEqual(r["equity_interval"][1], .5)

    def test_all_wins_clamped(self):
        self.assertEqual(equity_interval_from_shares(shares=[1]*100)["equity_interval"][1], 1)

    def test_all_losses_clamped(self):
        self.assertEqual(equity_interval_from_shares(shares=[0]*100)["equity_interval"][0], 0)

    def test_more_samples_narrower(self):
        a = equity_interval_from_shares(shares=[.5]*100)
        b = equity_interval_from_shares(shares=[.5]*1000)
        self.assertLess(b["equity_interval"][1]-b["equity_interval"][0],
                        a["equity_interval"][1]-a["equity_interval"][0])

    def test_invalid_shares(self):
        for samples in ([], [True], [float("nan")], [-.1], [1.1], "hello"):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                equity_interval_from_shares(shares=samples)

    def test_invalid_confidence(self):
        for c in (0, 1, -1, float("nan"), True):
            with self.subTest(c=c), self.assertRaises(ValueError):
                equity_interval_from_shares(shares=[.5], confidence=c)

    def test_positive_scenario(self):
        r = evaluate_sampled_call_scenarios(pot_before_call=100, call_cost=50,
            scenarios=[{"name": "tight", "shares": [1]*1000}])
        self.assertEqual(r["decision"], "CALL_POSITIVE_ALL_SCENARIOS")
        self.assertFalse(r["gto_solution"])
        self.assertFalse(r["range_uncertainty_included"])

    def test_two_scenarios_range_sensitive(self):
        r = evaluate_sampled_call_scenarios(pot_before_call=100, call_cost=50,
            scenarios=[{"name": "a", "shares": [0]*1000},
                       {"name": "b", "shares": [1]*1000}])
        self.assertEqual(r["decision"], "RANGE_SENSITIVE_OR_UNCERTAIN")
        self.assertAlmostEqual(r["sampled_scenarios"][0]["confidence"], .975)

    def test_duplicate_names(self):
        with self.assertRaises(ValueError):
            evaluate_sampled_call_scenarios(pot_before_call=100, call_cost=50,
                scenarios=[{"name": "x", "shares": [0]}, {"name": "x", "shares": [1]}])

    def test_invalid_schema(self):
        with self.assertRaises(ValueError):
            evaluate_sampled_call_scenarios(pot_before_call=100, call_cost=50,
                scenarios=[{"name": "x"}])

if __name__ == "__main__":
    unittest.main()
