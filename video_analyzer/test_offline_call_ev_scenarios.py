import unittest
from video_analyzer.offline_call_ev_scenarios import evaluate_call_scenarios as evaluate

class ScenariosTests(unittest.TestCase):
    def run_case(self, interval):
        return evaluate(pot_before_call=100, call_cost=50,
                        scenarios=[{"name": "a", "equity_interval": interval}])
    def test_positive(self):
        r = self.run_case([.6,.7])
        self.assertEqual(r["decision"], "CALL_POSITIVE_ALL_SCENARIOS")
        self.assertEqual(r["ev_envelope"], [40.,55.])
    def test_negative(self):
        self.assertEqual(self.run_case([0,.2])["decision"], "FOLD_NONNEGATIVE_ALL_SCENARIOS")
    def test_uncertain(self):
        r = evaluate(pot_before_call=100, call_cost=50, scenarios=[
            {"name":"a","equity_interval":[.2,.3]},
            {"name":"b","equity_interval":[.4,.5]}])
        self.assertEqual(r["decision"], "RANGE_SENSITIVE_OR_UNCERTAIN")
    def test_tie_not_robust(self):
        self.assertEqual(self.run_case([1/3,1/3])["decision"], "RANGE_SENSITIVE_OR_UNCERTAIN")
    def test_empty(self):
        with self.assertRaises(ValueError):
            evaluate(pot_before_call=100, call_cost=50, scenarios=[])
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            evaluate(pot_before_call=100, call_cost=50, scenarios=[
                {"name":"a","equity_interval":[0,1]}]*2)
    def test_invalid_equity(self):
        with self.assertRaises(ValueError): self.run_case([0,2])
    def test_no_claims(self):
        r = self.run_case([0,1])
        self.assertFalse(r["gto_solution"])
        self.assertFalse(r["hand_error_verified"])

if __name__ == "__main__":
    unittest.main()
