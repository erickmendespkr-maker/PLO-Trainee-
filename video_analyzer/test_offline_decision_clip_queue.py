"""Synthetic tests for offline visual review queue."""
import json
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_decision_clip_queue import build_review_queue, save_review_queue, QueueValidationError
except ImportError:
    from offline_decision_clip_queue import build_review_queue, save_review_queue, QueueValidationError

class ReviewQueueTests(unittest.TestCase):
    def sample(self):
        return dict(candidate_id="a", table_id=1, start_pts=2, end_pts=4, visual_confidence=0.5)
    def test_empty(self):
        self.assertEqual(build_review_queue([]), [])
    def test_low_confidence_first(self):
        a=self.sample(); b={**a, "candidate_id":"b", "visual_confidence":0.1}
        self.assertEqual([x["candidate_id"] for x in build_review_queue([a,b])], ["b","a"])
    def test_no_poker_claims(self):
        row=build_review_queue([self.sample()])[0]
        self.assertIsNone(row["strategic_conclusion"])
        self.assertFalse(row["hand_boundary_verified"])
        self.assertFalse(row["priority_is_ev"])
    def test_invalid_numbers(self):
        for field,value in [("start_pts",float("nan")),("end_pts",float("inf")),("visual_confidence",-0.1),("table_id",True)]:
            row=self.sample();row[field]=value
            with self.subTest(field=field), self.assertRaises(QueueValidationError):
                build_review_queue([row])
    def test_duplicate_ids(self):
        with self.assertRaises(QueueValidationError):
            build_review_queue([self.sample(),self.sample()])
    def test_four_table_limit(self):
        row=self.sample();row["table_id"]=5
        with self.assertRaises(QueueValidationError):
            build_review_queue([row])
    def test_review_flag_validation(self):
        row=self.sample();row["needs_human_review"]="yes"
        with self.assertRaises(QueueValidationError):
            build_review_queue([row])
    def test_save_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"review.json"
            save_review_queue([self.sample()],path)
            self.assertEqual(json.loads(path.read_text())["type"],"provisional_visual_review_queue")
            with self.assertRaises(FileExistsError):
                save_review_queue([],path)
    def test_deterministic_tie(self):
        a=self.sample();b={**a,"candidate_id":"b"}
        self.assertEqual(build_review_queue([b,a]),build_review_queue([a,b]))

if __name__=="__main__":
    unittest.main()
