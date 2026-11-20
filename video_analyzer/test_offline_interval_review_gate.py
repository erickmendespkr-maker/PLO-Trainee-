"""Synthetic regression tests for the conservative review gate."""
import unittest
from video_analyzer.offline_interval_review_gate import review_gate


def sample(**changes):
    record = dict(video_sha256="a" * 64, table_id=1, start_s=1.0,
                  end_s=10.0, hand_id="h1", status="reviewed",
                  reviewer="human", source="manual")
    record.update(changes)
    return record


class ReviewGateTests(unittest.TestCase):
    def test_reviewed_interval(self):
        self.assertEqual(review_gate(sample())["reason"], "HUMAN_REVIEWED_INTERVAL_ONLY")

    def test_ocr_proposal_requires_review(self):
        self.assertFalse(review_gate(sample(status="proposed", reviewer=None))["allowed"])

    def test_synthetic_cannot_confirm_real_hand(self):
        self.assertFalse(review_gate(sample(source="synthetic"))["allowed"])

    def test_reject_invalid_timestamp(self):
        self.assertFalse(review_gate(sample(start_s=10))["allowed"])

    def test_reject_invalid_table(self):
        self.assertFalse(review_gate(sample(table_id=True))["allowed"])

    def test_reject_invalid_hash(self):
        self.assertFalse(review_gate(sample(video_sha256="invalid"))["allowed"])


if __name__ == "__main__":
    unittest.main()
