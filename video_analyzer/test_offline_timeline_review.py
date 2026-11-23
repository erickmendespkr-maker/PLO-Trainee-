"""Tests for conservative integration of timeline and reviewed evidence."""
import copy
import unittest
try:
    from .offline_timeline_review import build_timeline_review
except ImportError:
    from offline_timeline_review import build_timeline_review

SHA = "a" * 64

def hand(table=1, start=2, end=14, verified=True):
    raw = {"table_id": table, "hand_start_s": start, "hand_end_s": end,
           "hero_cards": ["As","Ks","Qs","Js","Ts"], "board": ["2c","3d","4h"],
           "action": "call", "pot": 100, "amount": 20}
    return {"variant": "PLO5", "evidence": {
        k: {"value": v, "confidence": .99, "human_verified": verified}
        for k, v in raw.items()}}

class TimelineReviewTests(unittest.TestCase):
    def test_valid(self):
        r = build_timeline_review(SHA, [hand()], duration_s=60)
        self.assertTrue(r["hands"][0]["conditional_analysis_allowed"])
        self.assertFalse(r["hands"][0]["hand_boundaries_verified"])
        self.assertIsNone(r["hands"][0]["equity"])
    def test_overlaps_block_both(self):
        r = build_timeline_review(SHA, [hand(), hand(start=5,end=9)], duration_s=60)
        self.assertEqual(r["summary"]["ready_for_conditional_analysis"], 0)
        self.assertEqual(r["summary"]["timeline_review_required"], 2)
        self.assertTrue(all("SAME_TABLE_OVERLAP" in h["timeline_issue_codes"] for h in r["hands"]))
    def test_parallel_tables_allowed(self):
        r = build_timeline_review(SHA, [hand(), hand(table=2)], duration_s=60)
        self.assertEqual(r["summary"]["ready_for_conditional_analysis"], 2)
    def test_outside_video(self):
        r = build_timeline_review(SHA, [hand(end=70)], duration_s=60)
        self.assertEqual(r["hands"][0]["status"], "REVIEW_REQUIRED")
        self.assertFalse(r["hands"][0]["conditional_analysis_allowed"])
    def test_missing_table(self):
        r = build_timeline_review(SHA, [hand(table="table-1")], duration_s=60)
        self.assertEqual(r["hands"][0]["timeline_issue_codes"], ["UNKNOWN_TABLE"])
    def test_unverified_stays_blocked(self):
        r = build_timeline_review(SHA, [hand(verified=False)], duration_s=60)
        self.assertFalse(r["hands"][0]["conditional_analysis_allowed"])
        self.assertFalse(r["hands"][0]["evidence_gate_allowed"])
    def test_input_unchanged(self):
        hands = [hand()]
        original = copy.deepcopy(hands)
        build_timeline_review(SHA, hands, duration_s=60)
        self.assertEqual(hands, original)
    def test_bad_duration(self):
        with self.assertRaises(ValueError):
            build_timeline_review(SHA, [hand()], duration_s=0)

if __name__ == "__main__":
    unittest.main()
