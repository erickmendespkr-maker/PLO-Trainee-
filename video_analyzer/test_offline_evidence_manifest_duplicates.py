"""Regression tests for duplicate IDs in an offline evidence manifest."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from .offline_evidence_manifest import build_manifest


class DuplicateEvidenceTests(unittest.TestCase):
    def _fixture(self, path):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return dict(hand_id="h1", table_id=1, start_pts=0, end_pts=2,
                    video_sha256=sha, hole_cards_verified=True,
                    board_verified=True, action_verified=True,
                    pot_verified=True, call_cost_verified=True,
                    reviewed_by_human=True)

    def test_all_duplicate_entries_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.mp4"
            path.write_bytes(b"synthetic fixture; not a playable MP4")
            hand = self._fixture(path)
            report = build_manifest(path, [hand, dict(hand, start_pts=2, end_pts=4)],
                                    duration_seconds=10)
            self.assertEqual(report["reviewed_count"], 0)
            self.assertTrue(all(item["status"] == "INSUFFICIENT_DATA"
                                for item in report["hands"]))
            self.assertTrue(all("DUPLICATE_HAND_ID" in item["reasons"]
                                for item in report["hands"]))

    def test_identical_ids_on_distinct_tables_are_not_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.mp4"
            path.write_bytes(b"synthetic fixture; not a playable MP4")
            hand = self._fixture(path)
            report = build_manifest(path, [hand, dict(hand, table_id=2)],
                                    duration_seconds=10)
            self.assertEqual(report["reviewed_count"], 2)


if __name__ == "__main__":
    unittest.main()
