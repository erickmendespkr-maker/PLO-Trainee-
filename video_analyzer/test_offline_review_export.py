"""Regression tests for offline review-only export."""
import unittest
from offline_review_export import export_review_report

H = "a" * 64
R = "b" * 64


def sample():
    evidence = {"table_id": "1", "earliest_pts": 1, "latest_pts": 2}
    handoff = {"source": "offline_recorded_video", "video_sha256": H,
               "equity_or_ev_computed": False, "mp4_exported": False,
               "tasks": [{"review_id": R, "review_status": "PENDING",
                          "strategic_commentary_allowed": False, "evidence": evidence}]}
    journal = {"source": "offline_recorded_video", "video_sha256": H,
               "journal_sha256": "c" * 64,
               "entries": [{"review_id": R, "evidence": evidence,
                            "strategic_commentary_allowed": False,
                            "equity_or_ev_computed": False,
                            "decision": {"status": "REVIEWED", "reviewer_note": "checked"}}]}
    return handoff, journal


class ReviewExportTests(unittest.TestCase):
    def test_review_only(self):
        h, j = sample()
        result = export_review_report(h, j)
        self.assertEqual(result["reviewed_count"], 1)
        self.assertEqual(result["hands_confirmed"], 0)
        self.assertFalse(result["strategic_commentary_allowed"])

    def test_empty(self):
        h, j = sample()
        h["tasks"] = []
        j["entries"] = []
        self.assertEqual(export_review_report(h, j)["review_count"], 0)

    def test_hash_mismatch(self):
        h, j = sample()
        j["video_sha256"] = "d" * 64
        with self.assertRaises(ValueError):
            export_review_report(h, j)

    def test_evidence_mismatch(self):
        h, j = sample()
        j["entries"][0]["evidence"] = {"table_id": "2"}
        with self.assertRaises(ValueError):
            export_review_report(h, j)

    def test_missing_task(self):
        h, j = sample()
        h["tasks"] = []
        with self.assertRaises(ValueError):
            export_review_report(h, j)

    def test_duplicate_task(self):
        h, j = sample()
        h["tasks"].append(h["tasks"][0])
        with self.assertRaises(ValueError):
            export_review_report(h, j)

    def test_forbidden_claim(self):
        h, j = sample()
        j["entries"][0]["equity_or_ev_computed"] = True
        with self.assertRaises(ValueError):
            export_review_report(h, j)

    def test_handoff_export_claim(self):
        h, j = sample()
        h["mp4_exported"] = True
        with self.assertRaises(ValueError):
            export_review_report(h, j)


if __name__ == "__main__":
    unittest.main()
