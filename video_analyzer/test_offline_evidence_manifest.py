"""Synthetic provenance regression tests; no real footage required."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from .offline_evidence_manifest import build_manifest, validate_hand_evidence, manifest_json

class EvidenceManifestTests(unittest.TestCase):
    def setUp(self):
        self.sha = hashlib.sha256(b"synthetic-video").hexdigest()
        self.hand = dict(hand_id="h1", table_id=1, start_pts=0.5, end_pts=3.5,
                         video_sha256=self.sha, hole_cards_verified=True,
                         board_verified=True, action_verified=True, pot_verified=True,
                         call_cost_verified=True, reviewed_by_human=True)

    def audit(self):
        return validate_hand_evidence(self.hand, video_sha256=self.sha, duration_seconds=5)

    def test_reviewed(self):
        self.assertEqual(self.audit()["status"], "REVIEWED_EVIDENCE")
        self.assertEqual(self.audit()["strategic_verdict"], "NOT_ESTABLISHED")

    def test_missing_review(self):
        self.hand["reviewed_by_human"] = False
        self.assertIn("UNVERIFIED_REVIEWED_BY_HUMAN", self.audit()["reasons"])

    def test_video_mismatch(self):
        self.hand["video_sha256"] = "0" * 64
        self.assertIn("VIDEO_SHA_MISMATCH", self.audit()["reasons"])

    def test_bounds(self):
        self.hand["end_pts"] = 5.1
        self.assertIn("PTS_OUT_OF_BOUNDS", self.audit()["reasons"])

    def test_boolean_table_rejected(self):
        self.hand["table_id"] = True
        self.assertIn("TABLE_ID_INVALID", self.audit()["reasons"])

    def test_nan_rejected(self):
        self.hand["start_pts"] = float("nan")
        self.assertIn("PTS_OUT_OF_BOUNDS", self.audit()["reasons"])

    def test_invalid_sha(self):
        with self.assertRaises(ValueError):
            validate_hand_evidence(self.hand, video_sha256="not-a-sha", duration_seconds=5)

    def test_synthetic_file_hash_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(b"synthetic-video")
            result = build_manifest(path, [self.hand], duration_seconds=5, expected_sha256=self.sha)
            self.assertEqual(result["reviewed_count"], 1)
            self.assertEqual(json.loads(manifest_json(result))["video_sha256"], self.sha)

    def test_wrong_expected_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(b"synthetic-video")
            with self.assertRaises(ValueError):
                build_manifest(path, [], duration_seconds=5, expected_sha256="0" * 64)

    def test_duplicate_hand_ids_are_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(b"synthetic-video")
            result = build_manifest(path, [self.hand, self.hand], duration_seconds=5)
            self.assertEqual(result["reviewed_count"], 0)
            self.assertEqual([x["status"] for x in result["hands"]], ["INSUFFICIENT_DATA"] * 2)
            for entry in result["hands"]:
                self.assertIn("DUPLICATE_HAND_ID", entry["reasons"])

    def test_same_hand_id_on_distinct_tables_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(b"synthetic-video")
            other_table = dict(self.hand, table_id=2)
            result = build_manifest(path, [self.hand, other_table], duration_seconds=5)
            self.assertEqual(result["reviewed_count"], 2)
            self.assertTrue(all(x["status"] == "REVIEWED_EVIDENCE" for x in result["hands"]))

if __name__ == "__main__":
    unittest.main()
