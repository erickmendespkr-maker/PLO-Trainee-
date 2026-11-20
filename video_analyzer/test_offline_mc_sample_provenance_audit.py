"""Regression tests for conditional Monte Carlo sample provenance."""
import hashlib
import json
import unittest

from offline_mc_sample_provenance_audit import audit_sample_provenance


class SampleProvenanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.samples = {"tight": [0.0, 0.5, 1.0]}
        digest = hashlib.sha256(json.dumps(self.samples["tight"], separators=(",", ":")).encode()).hexdigest()
        self.report = {
            "schema_version": 1, "equity_engine_executed": False,
            "strategic_verdict_allowed": False, "gto_solution": False,
            "sampling_provenance": {"tight": {"seed": 7, "range_description": "hypothetical tight range",
                                               "sample_count": 3, "samples_sha256": digest}},
            "calculation": {"strategic_verdict_allowed": False, "gto_solution": False,
                            "scenarios": {"tight": {"samples": 3, "equity_estimate": 0.5,
                                                   "equity_lower": 0.0, "equity_upper": 1.0,
                                                   "ev_lower": -5.0, "ev_estimate": 0.0, "ev_upper": 5.0}}}
        }

    def test_valid(self):
        self.assertEqual(audit_sample_provenance(self.report, self.samples)["sample_hashes_verified"], 1)

    def test_tampered_samples(self):
        self.samples["tight"][0] = 0.25
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)

    def test_tampered_count(self):
        self.report["sampling_provenance"]["tight"]["sample_count"] = 4
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)

    def test_tampered_equity(self):
        self.report["calculation"]["scenarios"]["tight"]["equity_estimate"] = 0.8
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)

    def test_gto_claim_rejected(self):
        self.report["gto_solution"] = True
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)

    def test_missing_scenario(self):
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, {})

    def test_nonfinite_samples(self):
        self.samples["tight"][0] = float("nan")
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)

    def test_boolean_seed_rejected(self):
        self.report["sampling_provenance"]["tight"]["seed"] = True
        with self.assertRaises(ValueError):
            audit_sample_provenance(self.report, self.samples)


if __name__ == "__main__":
    unittest.main()
