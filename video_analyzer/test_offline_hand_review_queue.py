"""Synthetic regression checks for conservative human-review interval proposals."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from offline_hand_review_queue import propose_review_intervals, write_review_queue

def fixture():
    def event(t, i, pts, h):
        return {"table_id": t, "frame_index": i, "crop_pts_seconds": pts,
                "rgb_sha256": h * 64, "review_status": "UNREVIEWED"}
    return {"status": "UNREVIEWED_TIMELINE", "events": [
        event(1, 0, 0, "a"), event(2, 0, 0, "b"), event(1, 10, 1, "c"),
        event(2, 10, 1, "b"), event(1, 20, 2, "c")],
        "absolute_source_pts_verified": False, "hand_boundaries_verified": False,
        "ocr_verified": False, "equity_ev_verified": False}

class ReviewQueueTests(unittest.TestCase):
    def test_change_only(self):
        result = propose_review_intervals(fixture())
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["table_id"], 1)
        self.assertFalse(result["proposals"][0]["hand_confirmed"])
    def test_determinism(self):
        self.assertEqual(propose_review_intervals(fixture()), propose_review_intervals(fixture()))
    def test_claim_rejected(self):
        data = fixture(); data["hand_boundaries_verified"] = True
        with self.assertRaises(ValueError): propose_review_intervals(data)
    def test_duplicate_rejected(self):
        data = fixture(); data["events"].append(copy.deepcopy(data["events"][0]))
        with self.assertRaises(ValueError): propose_review_intervals(data)
    def test_negative_pts_rejected(self):
        data = fixture(); data["events"][2]["crop_pts_seconds"] = -1
        with self.assertRaises(ValueError): propose_review_intervals(data)
    def test_bad_hash_rejected(self):
        data = fixture(); data["events"][0]["rgb_sha256"] = "invalid"
        with self.assertRaises(ValueError): propose_review_intervals(data)
    def test_boolean_gap_rejected(self):
        with self.assertRaises(ValueError): propose_review_intervals(fixture(), min_gap_seconds=True)
    def test_gap_filter(self):
        self.assertEqual(propose_review_intervals(fixture(), max_gap_seconds=0.5)["proposals"], [])
    def test_write_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"in.json", Path(tmp)/"out.json"
            src.write_text(json.dumps(fixture()), encoding="utf-8")
            write_review_queue(src, dst)
            self.assertEqual(len(json.loads(dst.read_text(encoding="utf-8"))["proposals"]), 1)
            with self.assertRaises(FileExistsError): write_review_queue(src, dst)
    def test_nominal_source_claim_rejected(self):
        data = fixture()
        data["events"][0]["nominal_source_seconds"] = 0
        data["events"][0]["nominal_source_seconds_verified"] = True
        with self.assertRaises(ValueError): propose_review_intervals(data)

if __name__ == "__main__":
    unittest.main()
