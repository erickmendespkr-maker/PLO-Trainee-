import unittest
from offline_clip_plan_gate import plan_clip

BASE = dict(video_sha256="a"*64, table_id=1, hand_id="h1", start_seconds=1,
            end_seconds=4, duration_seconds=60, review_status="confirmed", output_name="h1.mp4")

class ClipPlanTests(unittest.TestCase):
    def test_valid(self):
        result = plan_clip(**BASE)
        self.assertEqual(result["duration_seconds"], 3)
        self.assertFalse(result["strategic_verdict_allowed"])
    def test_insufficient(self):
        self.assertEqual(plan_clip(**(BASE | {"review_status":"insufficient_data"}))["annotation"], "INSUFFICIENT_DATA")
    def test_bad_table(self):
        with self.assertRaises(ValueError):
            plan_clip(**(BASE | {"table_id": True}))
    def test_bad_times(self):
        with self.assertRaises(ValueError):
            plan_clip(**(BASE | {"end_seconds":61}))
    def test_nan(self):
        with self.assertRaises(ValueError):
            plan_clip(**(BASE | {"start_seconds":float("nan")}))
    def test_path_traversal(self):
        with self.assertRaises(ValueError):
            plan_clip(**(BASE | {"output_name":"../escape.mp4"}))
    def test_hash(self):
        with self.assertRaises(ValueError):
            plan_clip(**(BASE | {"video_sha256":"x"*64}))

if __name__ == "__main__":
    unittest.main()
