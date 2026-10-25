"""Offline-only synthetic tests for human OCR review decisions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_review_decisions import (
    handoff_sha256, validate_submission, load_submission, review_job, export_review
)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = "b" * 32
        self.folder = self.root / self.job_id
        self.folder.mkdir()
        self.store = Mock()
        self.handoff = {
            "schema_version": 1,
            "analysis_status": "unapproved_offline_review_handoff",
            "requires_manual_review": True,
            "ready_for_equity_or_ev": False,
            "job_id": self.job_id,
            "source_sha256": "a" * 64,
            "frames": [
                {"table_id": 1, "nominal_timestamp_seconds": 0.0,
                 "ocr_hints_unverified": [
                     {"field": "pot", "candidate_index": 0, "unverified_text": "120"},
                     {"field": "board", "candidate_index": 1, "unverified_text": "As Kh Qc"}]},
                {"table_id": 2, "nominal_timestamp_seconds": 2.0,
                 "ocr_hints_unverified": [
                     {"field": "hero_cards", "candidate_index": 2,
                      "unverified_text": "Ac Kd Qh Js 9c"}]}
            ]
        }
        self.submission = {
            "schema_version": 1, "job_id": self.job_id,
            "handoff_sha256": handoff_sha256(self.handoff),
            "reviewer": "human-reviewer-1",
            "decisions": [self.decision()]
        }

    def decision(self, *, table=1, stamp=0.0, field="pot", idx=0, status="confirmed",
                 value="120", confidence=0.9, reason="Valor legível no quadro"):
        return {"table_id": table, "nominal_timestamp_seconds": stamp, "field": field,
                "candidate_index": idx, "status": status, "value": value,
                "confidence": confidence, "reason": reason}

    def validate(self):
        return validate_submission(self.handoff, self.submission)

    def test_confirmed_partial(self):
        report = self.validate()
        self.assertEqual(report["reviewed_count"], 1)
        self.assertEqual(report["unreviewed_count"], 2)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["hand_reconstruction_verified"])

    def test_full_review_does_not_enable_math(self):
        self.submission["decisions"] += [
            self.decision(field="board", idx=1, status="corrected",
                          value="As Kh Qd", confidence=0.7, reason="Corrigido olhando quadro"),
            self.decision(table=2, stamp=2, field="hero_cards", idx=2,
                          status="uncertain", value=None, confidence=None,
                          reason="Cartas ilegíveis")
        ]
        report = self.validate()
        self.assertEqual(report["unreviewed_count"], 0)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["automatic_clip_selection_authorized"])
        self.assertEqual(report["status_counts"]["corrected"], 1)

    def test_corrected_differs_from_ocr(self):
        self.submission["decisions"][0]["status"] = "corrected"
        with self.assertRaisesRegex(ValueError, "differ"): self.validate()

    def test_confirmed_must_match_ocr(self):
        self.submission["decisions"][0]["value"] = "121"
        with self.assertRaisesRegex(ValueError, "differs"): self.validate()

    def test_rejected_must_have_no_value(self):
        self.submission["decisions"][0]["status"] = "rejected"
        with self.assertRaisesRegex(ValueError, "cannot contain"): self.validate()

    def test_uncertain_without_value(self):
        self.submission["decisions"][0].update(status="uncertain", value=None, confidence=None)
        self.assertEqual(self.validate()["status_counts"]["uncertain"], 1)

    def test_unknown_candidate_rejected(self):
        self.submission["decisions"][0]["candidate_index"] = 999
        with self.assertRaisesRegex(ValueError, "Unknown"): self.validate()

    def test_cross_table_rejected(self):
        self.submission["decisions"][0]["table_id"] = 3
        with self.assertRaisesRegex(ValueError, "Unknown"): self.validate()

    def test_timestamp_tamper_rejected(self):
        self.submission["decisions"][0]["nominal_timestamp_seconds"] = 0.01
        with self.assertRaisesRegex(ValueError, "Unknown"): self.validate()

    def test_duplicate_decisions_rejected(self):
        self.submission["decisions"].append(copy.deepcopy(self.submission["decisions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"): self.validate()

    def test_handoff_mutation_rejected(self):
        self.handoff["frames"][0]["ocr_hints_unverified"][0]["unverified_text"] = "999"
        with self.assertRaisesRegex(ValueError, "fingerprint"): self.validate()

    def test_job_id_mismatch_rejected(self):
        self.submission["job_id"] = "c" * 32
        with self.assertRaisesRegex(ValueError, "Job ID"): self.validate()

    def test_unexpected_fields_rejected(self):
        self.submission["decisions"][0]["ready_for_equity_or_ev"] = True
        with self.assertRaisesRegex(ValueError, "structure"): self.validate()

    def test_nan_and_bool_confidence_rejected(self):
        for invalid in (float("nan"), float("inf"), True, -0.1, 1.01):
            with self.subTest(invalid=invalid):
                self.submission["decisions"][0]["confidence"] = invalid
                with self.assertRaises(ValueError): self.validate()

    def test_bad_reviewer_or_reason_rejected(self):
        self.submission["reviewer"] = " "
        with self.assertRaises(ValueError): self.validate()
        self.submission["reviewer"] = "human-reviewer-1"
        self.submission["decisions"][0]["reason"] = "x"
        with self.assertRaises(ValueError): self.validate()

    def test_submission_duplicate_json_keys_rejected(self):
        p = self.root / "submission.json"
        p.write_text('{"job_id":"a","job_id":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"): load_submission(p)

    def test_symlink_submission_rejected(self):
        p = self.root / "submission.json"
        p.write_text("{}", encoding="utf-8")
        link = self.root / "link.json"
        link.symlink_to(p)
        with self.assertRaisesRegex(ValueError, "safely"): load_submission(link)

    def test_nonfinite_json_rejected(self):
        p = self.root / "submission.json"
        p.write_text('{"x": NaN}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Non-finite"): load_submission(p)

    def test_large_json_rejected(self):
        p = self.root / "large.json"
        p.write_bytes(b" " * 2_000_001)
        with self.assertRaisesRegex(ValueError, "size limit"): load_submission(p)

    def test_export_write_once_and_queue_untouched(self):
        with patch("offline_job_review_decisions.build_handoff", return_value=self.handoff):
            report = export_review(self.store, self.job_id, self.root, self.submission)
            p = self.folder / "human_ocr_review.json"
            self.assertTrue(p.is_file())
            self.assertEqual(json.loads(p.read_text())["reviewed_count"], 1)
            with self.assertRaises(FileExistsError):
                export_review(self.store, self.job_id, self.root, self.submission)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.store.transition.assert_not_called()
        self.store.claim_next.assert_not_called()

    def test_reaudit_before_export(self):
        altered = copy.deepcopy(self.handoff)
        altered["frames"][0]["ocr_hints_unverified"][0]["unverified_text"] = "200"
        with patch("offline_job_review_decisions.build_handoff", return_value=altered):
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                export_review(self.store, self.job_id, self.root, self.submission)
        self.assertFalse((self.folder / "human_ocr_review.json").exists())

    def test_real_handoff_audit_binding(self):
        # Reuse the full synthetic source/frame/job fixture from the previous cycle.
        from test_offline_job_review_handoff import HandoffTests
        fixture = HandoffTests("test_unapproved_ocr_linked")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.ocr(text="120", field="pot")
        handoff = fixture.build()
        sub = {"schema_version": 1, "job_id": fixture.job_id,
               "handoff_sha256": handoff_sha256(handoff), "reviewer": "reviewer",
               "decisions": [self.decision()]}
        result = review_job(fixture.store, fixture.job_id, fixture.root / "results", sub)
        self.assertEqual(result["reviewed_count"], 1)
        self.assertFalse(result["ready_for_equity_or_ev"])
        fixture.image.write_bytes(fixture.image.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            review_job(fixture.store, fixture.job_id, fixture.root / "results", sub)


if __name__ == "__main__":
    unittest.main()
