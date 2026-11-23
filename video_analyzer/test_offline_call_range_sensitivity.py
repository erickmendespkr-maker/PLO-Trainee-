import unittest
from video_analyzer.offline_call_range_sensitivity import evaluate_call_scenarios

def scenario(name, equity, lo, hi):
    return {"name": name, "range_assumption": "hypothetical " + name,
            "equity": equity, "equity_ci": [lo, hi]}

class TestRangeSensitivity(unittest.TestCase):
    def test_positive(self):
        r = evaluate_call_scenarios(100, 50, [scenario("tight", .6, .55, .65)])
        self.assertEqual(r["classification"], "POSITIVE_IN_ALL_SUPPLIED_SCENARIOS")
        self.assertAlmostEqual(r["scenario_envelope_ev_chips"][0], 32.5)

    def test_negative(self):
        r = evaluate_call_scenarios(100, 50, [scenario("tight", .2, .1, .3)])
        self.assertEqual(r["classification"], "NEGATIVE_IN_ALL_SUPPLIED_SCENARIOS")

    def test_sensitive(self):
        r = evaluate_call_scenarios(100, 50, [scenario("a", .2, .1, .3),
                                              scenario("b", .6, .5, .7)])
        self.assertEqual(r["classification"], "RANGE_OR_SAMPLING_SENSITIVE")
        self.assertFalse(r["scenario_envelope_is_confidence_interval"])
        self.assertEqual(r["strategic_verdict"], "NOT_ESTABLISHED")

    def test_zero_boundary(self):
        r = evaluate_call_scenarios(100, 50, [scenario("a", 1/3, 1/3, 1/3)])
        self.assertEqual(r["classification"], "RANGE_OR_SAMPLING_SENSITIVE")

    def test_missing_interval(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(100, 50, [{"name": "a", "range_assumption": "x", "equity": .5}])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(100, 50, [scenario("a", .5, .4, .6)] * 2)

    def test_bad_equity(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(100, 50, [scenario("a", float("nan"), .1, .9)])

    def test_no_scenarios(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(100, 50, [])

if __name__ == "__main__":
    unittest.main()
