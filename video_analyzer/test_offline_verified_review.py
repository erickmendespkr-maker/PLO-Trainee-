"""Synthetic regression tests for the combined offline evidence gate."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from video_analyzer.offline_verified_review import verified_review_gate


def sha(data):
    return hashlib.sha256(data).hexdigest()


class VerifiedReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.video = root / "source.mp4"
        self.frames = root / "frames"
        self.frames.mkdir()
        self.video.write_bytes(b"video-fixture")
        (self.frames / "frame.png").write_bytes(b"frame-fixture")
        source_hash = sha(b"video-fixture")
        self.hand = {
            "review_status": "HUMAN_CONFIRMED", "game": "PLO5", "table_id": 1,
            "hand_start_seconds": 10, "hand_end_seconds": 20,
            "hero_cards": ["Ac", "Kd", "Qh", "Js", "Tc"],
            "board_cards": ["2c", "3d", "4h"], "action": "call",
            "pot_before_action": 100, "amount_to_call": 25,
            "source_video_sha256": source_hash,
            "range_assumptions": {"villain": "hypothetical"},
            "model_assumptions": {"future_bets": "none"},
            "evidence": [{"human_verified": True, "pts_seconds": 15,
                          "frame_sha256": sha(b"frame-fixture"),
                          "frame_file": "frame.png", "table_id": 1,
                          "source_video_sha256": source_hash}]
        }

    def gate(self):
        return verified_review_gate(self.hand, self.video, self.frames)

    def test_valid_conditional(self):
        r = self.gate()
        self.assertEqual(r["status"], "CONDITIONAL_ANALYSIS_PERMITTED")
        self.assertEqual(r["verified_file_count"], 1)
        self.assertFalse(r["proves_frame_origin"])
        self.assertFalse(r["gto_claim_permitted"])

    def test_unreviewed(self):
        self.hand["review_status"] = "PENDING"
        self.assertEqual(self.gate()["status"], "INSUFFICIENT_DATA")

    def test_frame_tampered(self):
        (self.frames / "frame.png").write_bytes(b"tampered")
        self.assertIn("frame_0_hash_mismatch", self.gate()["reasons"])

    def test_video_tampered(self):
        self.video.write_bytes(b"tampered")
        self.assertIn("source_hash_mismatch", self.gate()["reasons"])

    def test_missing_frame(self):
        (self.frames / "frame.png").unlink()
        self.assertEqual(self.gate()["status"], "INSUFFICIENT_DATA")

    def test_missing_range(self):
        self.hand["range_assumptions"] = {}
        self.assertIn("opponent_range_missing", self.gate()["reasons"])

    def test_wrong_timestamp(self):
        self.hand["evidence"][0]["pts_seconds"] = 21
        self.assertIn("frame_evidence_unverified", self.gate()["reasons"])

    def test_bad_record(self):
        r = verified_review_gate(None, self.video, self.frames)
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")

    def test_missing_video(self):
        self.video.unlink()
        self.assertEqual(self.gate()["status"], "INSUFFICIENT_DATA")

    def test_unsafe_frame_path(self):
        self.hand["evidence"][0]["frame_file"] = "../source.mp4"
        self.assertEqual(self.gate()["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
