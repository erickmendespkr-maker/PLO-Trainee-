"""Regression tests for the offline review report integrity boundary."""
import copy
import unittest

try:
    from .offline_review_journal import create_review_journal
    from .offline_review_export import export_review_report
except ImportError:
    from offline_review_journal import create_review_journal
    from offline_review_export import export_review_report


class ReviewExportIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "schema_version": 1,
            "source": "offline_recorded_video",
            "video_sha256": "a" * 64,
            "equity_or_ev_computed": False,
            "mp4_exported": False,
            "tasks": [{
                "review_id": "b" * 64,
                "review_status": "PENDING",
                "strategic_commentary_allowed": False,
                "evidence": {"earliest_pts": 1.0, "latest_pts": 2.0},
            }],
        }
        self.journal = create_review_journal(self.handoff)

    def test_valid_journal_export(self):
        result = export_review_report(self.handoff, self.journal)
        self.assertEqual(result["review_count"], 1)
        self.assertFalse(result["equity_or_ev_computed"])

    def test_tampered_review_rejected(self):
        journal = copy.deepcopy(self.journal)
        journal["entries"][0]["decision"]["status"] = "REVIEWED"
        with self.assertRaisesRegex(ValueError, "integrity"):
            export_review_report(self.handoff, journal)

    def test_missing_digest_rejected(self):
        journal = copy.deepcopy(self.journal)
        del journal["journal_sha256"]
        with self.assertRaises(ValueError):
            export_review_report(self.handoff, journal)

    def test_invalid_video_hash_rejected(self):
        handoff = copy.deepcopy(self.handoff)
        handoff["video_sha256"] = "not-a-hash"
        journal = copy.deepcopy(self.journal)
        journal["video_sha256"] = "not-a-hash"
        with self.assertRaises(ValueError):
            export_review_report(handoff, journal)

    def test_missing_strategic_boundary_rejected(self):
        journal = copy.deepcopy(self.journal)
        journal["requires_separate_strategic_evidence_validation"] = False
        with self.assertRaises(ValueError):
            export_review_report(self.handoff, journal)

    def test_unsupported_schema_rejected(self):
        handoff = copy.deepcopy(self.handoff)
        handoff["schema_version"] = 2
        with self.assertRaises(ValueError):
            export_review_report(handoff, self.journal)


if __name__ == "__main__":
    unittest.main()
