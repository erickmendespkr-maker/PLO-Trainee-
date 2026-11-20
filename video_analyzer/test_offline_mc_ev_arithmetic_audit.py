"""Regression tests for independent conditional EV arithmetic audit."""
import unittest
from offline_mc_ev_arithmetic_audit import audit_mc_ev_arithmetic
from offline_mc_ev_uncertainty import conditional_mc_call_ev

def fixture():
    shares = {"tight": [0.1, 0.3, 0.6, 1.0] * 20, "loose": [0.2, 0.8] * 40}
    return ({"schema_version": 1, "model_scope": "hypothetical_heads_up_single_call",
             "gto_solution": False, "strategic_verdict_allowed": False,
             "equity_engine_executed": False,
             "calculation": conditional_mc_call_ev(100, 20, shares, rake=2)}, shares)

class AuditTests(unittest.TestCase):
    def check_bad(self, transform):
        report, shares = fixture()
        transform(report, shares)
        with self.assertRaises(ValueError):
            audit_mc_ev_arithmetic(report, shares, pot_before_call=100, call_cost=20, rake=2)

    def test_valid(self):
        report, shares = fixture()
        self.assertTrue(audit_mc_ev_arithmetic(report, shares, pot_before_call=100, call_cost=20, rake=2)["ev_arithmetic_verified"])

    def test_ev_tampering(self):
        self.check_bad(lambda r, s: r["calculation"]["scenarios"]["tight"].__setitem__("ev_estimate", 999))

    def test_bound_tampering(self):
        self.check_bad(lambda r, s: r["calculation"]["scenarios"]["tight"].__setitem__("equity_lower", 0.01))

    def test_envelope_tampering(self):
        self.check_bad(lambda r, s: r["calculation"].__setitem__("ev_envelope", [-100, 100]))

    def test_signal_tampering(self):
        self.check_bad(lambda r, s: r["calculation"].__setitem__("conditional_signal", "negative_across_scenarios"))

    def test_sample_tampering(self):
        self.check_bad(lambda r, s: s["tight"].__setitem__(0, 0.99))

    def test_scenario_mismatch(self):
        self.check_bad(lambda r, s: s.pop("loose"))

    def test_gto_claim(self):
        self.check_bad(lambda r, s: r.__setitem__("gto_solution", True))

    def test_ocr_claim(self):
        self.check_bad(lambda r, s: r["calculation"].__setitem__("ocr_uncertainty_included", True))

    def test_nan(self):
        self.check_bad(lambda r, s: r["calculation"]["scenarios"]["tight"].__setitem__("ev_upper", float("nan")))

    def test_invalid_cost(self):
        report, shares = fixture()
        with self.assertRaises(ValueError):
            audit_mc_ev_arithmetic(report, shares, pot_before_call=100, call_cost=True, rake=2)

if __name__ == "__main__":
    unittest.main()
