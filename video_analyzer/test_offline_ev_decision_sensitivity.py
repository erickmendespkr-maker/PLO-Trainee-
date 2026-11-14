import unittest
from offline_ev_decision_sensitivity import compare_scenarios

def scenario(sid, fold=(0, 0), call=(1, 2), raise_ev=(3, 4)):
    return {"scenario_id": sid, "assumptions": {"opponent_range": "hypothetical", "rake": 0},
            "ev_intervals": {"fold": fold, "call": call, "raise": raise_ev}}

class ComparisonTests(unittest.TestCase):
    def test_robust_raise(self):
        r = compare_scenarios([scenario("tight"), scenario("loose", call=(0, 1), raise_ev=(2, 3))])
        self.assertEqual(r["preferred_action"], "raise")
        self.assertFalse(r["gto_solution"])
    def test_range_sensitive(self):
        self.assertIsNone(compare_scenarios([scenario("a"), scenario("b", call=(5, 6), raise_ev=(1, 2))])["preferred_action"])
    def test_overlap(self):
        self.assertIsNone(compare_scenarios([scenario("a", call=(2, 4))])["preferred_action"])
    def test_margin(self):
        self.assertIsNone(compare_scenarios([scenario("a")], min_gap=1)["preferred_action"])
    def test_no_scenarios(self):
        with self.assertRaises(ValueError): compare_scenarios([])
    def test_nan(self):
        with self.assertRaises(ValueError): compare_scenarios([scenario("a", call=(float("nan"), 2))])
    def test_duplicate(self):
        with self.assertRaises(ValueError): compare_scenarios([scenario("a"), scenario("a")])
    def test_missing_action(self):
        s = scenario("a"); del s["ev_intervals"]["fold"]
        with self.assertRaises(ValueError): compare_scenarios([s])
    def test_missing_assumptions(self):
        s = scenario("a"); s["assumptions"] = {}
        with self.assertRaises(ValueError): compare_scenarios([s])
    def test_boolean_ev_rejected(self):
        with self.assertRaises(ValueError): compare_scenarios([scenario("a", fold=(False, 0))])
    def test_invalid_gap(self):
        with self.assertRaises(ValueError): compare_scenarios([scenario("a")], min_gap=-1)

if __name__ == "__main__": unittest.main()
