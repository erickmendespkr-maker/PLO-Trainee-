"""Synthetic integrity tests for offline clip manifests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_clip_manifest_verify import verify_clip_manifest
except ImportError:
    from offline_clip_manifest_verify import verify_clip_manifest


class ManifestAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.clip, self.source = root / "clip.mp4", root / "source.mp4"
        self.clip.write_bytes(b"synthetic clip")
        self.source.write_bytes(b"synthetic source")
        self.data = {
            "schema_version": 1,
            "clip_sha256": hashlib.sha256(self.clip.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "requested_interval_seconds": [1, 3], "source_duration_seconds": 5,
            "table_id": 2, "gto_solution": False, "ev_is_conditional": True,
            "human_review_of_export": False,
            "evidence_gate": {"status": "REVIEW_REQUIRED", "table_id": 2,
                              "start_pts": 1, "end_pts": 3, "can_label_error": False,
                              "can_attach_conditional_ev": False}
        }

    def audit(self, source=None):
        self.clip.with_suffix(".json").write_text(json.dumps(self.data), encoding="utf-8")
        return verify_clip_manifest(self.clip, source=source)

    def test_valid(self):
        result = self.audit(self.source)
        self.assertTrue(result["valid"])
        self.assertFalse(result["human_review_verified"])

    def test_clip_tamper(self):
        self.clip.write_bytes(b"tampered")
        self.assertIn("clip_hash_mismatch", self.audit()["problems"])

    def test_source_tamper(self):
        self.source.write_bytes(b"tampered")
        self.assertIn("source_hash_mismatch", self.audit(self.source)["problems"])

    def test_gate_conflict(self):
        self.data["evidence_gate"]["can_attach_conditional_ev"] = True
        self.assertIn("inconsistent_evidence_gate", self.audit()["problems"])

    def test_gto_claim(self):
        self.data["gto_solution"] = True
        self.assertIn("unsupported_claims", self.audit()["problems"])

    def test_out_of_bounds(self):
        self.data["requested_interval_seconds"] = [1, 6]
        self.assertIn("invalid_interval", self.audit()["problems"])

    def test_missing_manifest(self):
        self.assertIn("manifest_unreadable", verify_clip_manifest(self.clip)["problems"])

    def test_invalid_sha(self):
        self.data["clip_sha256"] = "invalid"
        self.assertIn("invalid_clip_sha256", self.audit()["problems"])

    def test_conditional_not_human_review(self):
        self.data["evidence_gate"].update(status="APPROVED_CONDITIONAL", can_attach_conditional_ev=True)
        result = self.audit()
        self.assertTrue(result["valid"])
        self.assertFalse(result["human_review_verified"])


if __name__ == "__main__":
    unittest.main()
