import tempfile
import unittest
from pathlib import Path
from offline_batch_preflight import preflight_batch

def item(start=1, end=3, table=1, destination="clip.mp4"):
    return {"status": "PLANNED_ONLY", "human_review_required": True,
            "destination": destination,
            "record": {"table_id": table, "start_pts": start, "end_pts": end,
                       "table_verified": False, "hand_verified": False,
                       "hero_cards_verified": False, "board_verified": False,
                       "action_verified": False, "amounts_verified": False}}

class PreflightTests(unittest.TestCase):
    def test_valid_multitable(self):
        result = preflight_batch([item(), item(4, 7, 4, "two.mp4")], 10)
        self.assertEqual(result["total_seconds"], 5)
        self.assertEqual(result["status"], "NOT_EXPORTED")
    def test_empty(self):
        self.assertEqual(preflight_batch([], 10)["clips"], [])
    def test_invalid_intervals(self):
        for start, end in [(-1, 2), (3, 3), (4, 3), (0, 11), (float("nan"), 3)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                preflight_batch([item(start, end)], 10)
    def test_unsafe_flags(self):
        for key, value in [("status", "APPROVED"), ("human_review_required", False)]:
            candidate = item()
            candidate[key] = value
            with self.assertRaises(ValueError):
                preflight_batch([candidate], 10)
    def test_verified_record_rejected(self):
        candidate = item()
        candidate["record"]["hand_verified"] = True
        with self.assertRaises(ValueError):
            preflight_batch([candidate], 10)
    def test_invalid_tables(self):
        for table in [0, 5, True, "1"]:
            with self.assertRaises(ValueError):
                preflight_batch([item(table=table)], 10)
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            preflight_batch([item(), item(4, 5)], 10)
    def test_limits(self):
        with self.assertRaises(ValueError):
            preflight_batch([item()], 10, max_total_seconds=1)
        with self.assertRaises(ValueError):
            preflight_batch([item(), item(4, 5, destination="two.mp4")], 10, max_clips=1)
    def test_existing_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "clip.mp4"
            target.with_suffix(".json").write_text("{}")
            with self.assertRaises(FileExistsError):
                preflight_batch([item(destination=str(target))], 10)
    def test_bad_duration(self):
        for duration in [0, True, float("inf")]:
            with self.assertRaises(ValueError):
                preflight_batch([item()], duration)

if __name__ == "__main__":
    unittest.main()
