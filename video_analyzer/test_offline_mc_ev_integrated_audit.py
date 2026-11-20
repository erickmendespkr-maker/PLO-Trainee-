"""Regression tests for the offline conditional report integration."""
import copy
import unittest
from offline_mc_ev_integrated_audit import (build_and_audit_conditional_report,
    audit_report_monetary_assumptions)
from offline_mc_sample_provenance_audit import audit_sample_provenance
from offline_mc_ev_arithmetic_audit import audit_mc_ev_arithmetic


class IntegratedAuditTests(unittest.TestCase):
    def setUp(self):
        self.kw = dict(video_sha256="a" * 64, hand_id="synthetic-1",
                       reviewed=False, variant="PLO5", pot_before_call=100,
                       call_cost=50, scenarios={
                           "tight": {"seed": 1, "shares": [0.0, 0.5, 1.0],
                                     "range_description": "synthetic tight range"},
                           "wide": {"seed": 2, "shares": [1.0, 1.0, 0.0],
                                    "range_description": "synthetic wide range"}})

    def test_integrated_success(self):
        result = build_and_audit_conditional_report(**self.kw)
        self.assertEqual(result["audit"]["sample_hashes_verified"], 2)
        self.assertTrue(result["audit"]["ev_arithmetic_verified"])
        self.assertFalse(result["audit"]["strategic_verdict_allowed"])
        self.assertFalse(result["report"]["human_reviewed"])

    def test_determinism(self):
        self.assertEqual(build_and_audit_conditional_report(**self.kw),
                         build_and_audit_conditional_report(**self.kw))

    def test_invalid_share(self):
        kw = copy.deepcopy(self.kw)
        kw["scenarios"]["tight"]["shares"] = [float("nan")]
        with self.assertRaises(ValueError):
            build_and_audit_conditional_report(**kw)

    def test_invalid_money(self):
        kw = dict(self.kw, call_cost=0)
        with self.assertRaises(ValueError):
            build_and_audit_conditional_report(**kw)

    def test_hash_tamper(self):
        report = build_and_audit_conditional_report(**self.kw)["report"]
        report["sampling_provenance"]["tight"]["samples_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            audit_sample_provenance(report, {k: v["shares"] for k, v in self.kw["scenarios"].items()})

    def test_ev_tamper(self):
        report = build_and_audit_conditional_report(**self.kw)["report"]
        report["calculation"]["scenarios"]["wide"]["ev_estimate"] += 1
        with self.assertRaises(ValueError):
            audit_mc_ev_arithmetic(report,
                {k: v["shares"] for k, v in self.kw["scenarios"].items()},
                pot_before_call=100, call_cost=50)


    def test_monetary_binding_present(self):
        result = build_and_audit_conditional_report(**self.kw)
        self.assertTrue(result["audit"]["monetary_assumptions_integrity_verified"])
        self.assertFalse(result["audit"]["monetary_values_video_verified"])
        self.assertEqual(result["report"]["monetary_binding"]["assumptions"]["call_cost"], 50.0)

    def test_monetary_binding_rejects_different_cost(self):
        report = build_and_audit_conditional_report(**self.kw)["report"]
        with self.assertRaises(ValueError):
            audit_report_monetary_assumptions(report, pot_before_call=100, call_cost=51)

    def test_monetary_binding_rejects_tampered_hash(self):
        report = build_and_audit_conditional_report(**self.kw)["report"]
        report["monetary_binding"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            audit_report_monetary_assumptions(report, pot_before_call=100, call_cost=50)

    def test_monetary_binding_rejects_missing_record(self):
        report = build_and_audit_conditional_report(**self.kw)["report"]
        del report["monetary_binding"]
        with self.assertRaises(ValueError):
            audit_report_monetary_assumptions(report, pot_before_call=100, call_cost=50)

    def test_monetary_binding_unit_mismatch(self):
        report = build_and_audit_conditional_report(**self.kw, currency_unit="bb")["report"]
        with self.assertRaises(ValueError):
            audit_report_monetary_assumptions(report, pot_before_call=100, call_cost=50, currency_unit="chips")
        self.assertTrue(audit_report_monetary_assumptions(
            report, pot_before_call=100, call_cost=50, currency_unit="bb")[
                "monetary_assumptions_integrity_verified"])


if __name__ == "__main__":
    unittest.main()
