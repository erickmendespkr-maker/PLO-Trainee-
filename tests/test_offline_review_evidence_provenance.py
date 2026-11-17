"""Regression tests for provenance and timestamps of reviewed offline evidence."""
import unittest
from video_analyzer.offline_review_evidence_gate import review_gate

class EvidenceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.hand = {
            "review_status": "HUMAN_CONFIRMED", "game": "PLO5", "table_id": 2,
            "hand_start_seconds": 10.0, "hand_end_seconds": 20.0,
            "hero_cards": ["As", "Ks", "Qs", "Js", "Ts"],
            "board_cards": ["2c", "3d", "4h"], "action": "call",
            "pot_before_action": 100, "amount_to_call": 20,
            "source_video_sha256": "a" * 64,
            "evidence": [{"human_verified": True, "pts_seconds": 15.0,
                          "frame_sha256": "b" * 64,
                          "source_video_sha256": "a" * 64, "table_id": 2}],
            "range_assumptions": {"opponent": "hypothetical"},
            "model_assumptions": {"future_bets": "excluded"},
        }

    def test_valid_conditional_review(self):
        result = review_gate(self.hand)
        self.assertEqual(result["status"], "CONDITIONAL_ANALYSIS_PERMITTED")
        self.assertFalse(result["gto_claim_permitted"])

    def test_frame_before_hand(self):
        self.hand["evidence"][0]["pts_seconds"] = 9.9
        self.assertIn("frame_evidence_unverified", review_gate(self.hand)["reasons"])

    def test_frame_after_hand(self):
        self.hand["evidence"][0]["pts_seconds"] = 20.1
        self.assertIn("frame_evidence_unverified", review_gate(self.hand)["reasons"])

    def test_wrong_source_hash(self):
        self.hand["evidence"][0]["source_video_sha256"] = "c" * 64
        self.assertIn("source_video_link_unverified", review_gate(self.hand)["reasons"])

    def test_wrong_table(self):
        self.hand["evidence"][0]["table_id"] = 3
        self.assertIn("frame_table_link_unverified", review_gate(self.hand)["reasons"])

    def test_missing_source_hash(self):
        del self.hand["source_video_sha256"]
        self.assertIn("source_video_hash_missing", review_gate(self.hand)["reasons"])

    def test_bad_interval_does_not_crash(self):
        self.hand["hand_start_seconds"] = None
        self.assertEqual(review_gate(self.hand)["status"], "INSUFFICIENT_DATA")

if __name__ == "__main__":
    unittest.main()
