"""Regression tests for the actual review-history + timeline integration.

Run: python -m unittest video_analyzer.test_offline_timeline_review_integration
No video, network, credentials or poker service required.
"""
import copy
import unittest
from unittest.mock import patch

try:
    from . import offline_timeline_review as module
except ImportError:
    import offline_timeline_review as module


SHA = "a" * 64


def hand(table, start, end, *, allowed=True):
    return {
        "table_id": table,
        "start_s": start,
        "end_s": end,
        "status": "READY_FOR_CONDITIONAL_ANALYSIS" if allowed else "INSUFFICIENT_DATA",
        "conditional_analysis_allowed": allowed,
        "equity": None,
        "ev": None,
        "strategic_verification": False,
    }


def ledger(hands):
    return {
        "schema_version": 1,
        "source_video_sha256": SHA,
        "analysis_type": "OFFLINE_REVIEW_ONLY",
        "hands": hands,
        "summary": {
            "total": len(hands),
            "ready_for_conditional_analysis": sum(bool(h["conditional_analysis_allowed"]) for h in hands),
            "insufficient_data": sum(not h["conditional_analysis_allowed"] for h in hands),
        },
        "equity_or_ev_computed": False,
        "video_visual_accuracy_verified": False,
    }


class TimelineReviewIntegrationTests(unittest.TestCase):
    def build(self, hands, duration=120):
        original = ledger(hands)
        before = copy.deepcopy(original)
        with patch.object(module, "build_review_history", return_value=original) as mocked:
            result = module.build_timeline_review(SHA, [], duration_s=duration)
            mocked.assert_called_once()
        self.assertEqual(original, before, "input ledger was mutated")
        self.assertFalse(result["video_visual_accuracy_verified"])
        self.assertFalse(result["equity_or_ev_computed"])
        self.assertTrue(all(h["equity"] is None and h["ev"] is None for h in result["hands"]))
        return result

    def test_sequential_hands_remain_eligible_but_unverified(self):
        result = self.build([hand(1, 0, 10), hand(1, 10, 20)])
        self.assertEqual(result["summary"]["ready_for_conditional_analysis"], 2)
        self.assertEqual(result["summary"]["timeline_review_required"], 0)
        self.assertTrue(all(not h["hand_boundaries_verified"] for h in result["hands"]))

    def test_parallel_tables_are_not_overlaps(self):
        result = self.build([hand(1, 0, 20), hand(2, 0, 20), hand(3, 0, 20), hand(4, 0, 20)])
        self.assertEqual(result["timeline_audit"]["issues"], [])
        self.assertEqual(result["summary"]["ready_for_conditional_analysis"], 4)

    def test_both_overlapping_hands_blocked(self):
        result = self.build([hand(1, 0, 20), hand(1, 10, 30)])
        self.assertEqual(result["summary"]["timeline_review_required"], 2)
        self.assertEqual(result["summary"]["ready_for_conditional_analysis"], 0)
        for h in result["hands"]:
            self.assertEqual(h["status"], "REVIEW_REQUIRED")
            self.assertTrue(h["evidence_gate_allowed"])
            self.assertIn("SAME_TABLE_OVERLAP", h["timeline_issue_codes"])

    def test_invalid_table_and_out_of_video_blocked(self):
        result = self.build([hand(5, 0, 10), hand(1, 110, 130)])
        self.assertEqual(result["summary"]["ready_for_conditional_analysis"], 0)
        self.assertEqual(result["hands"][0]["timeline_issue_codes"], ["UNKNOWN_TABLE"])
        self.assertEqual(result["hands"][1]["timeline_issue_codes"], ["OUTSIDE_VIDEO"])

    def test_existing_insufficient_data_is_not_promoted(self):
        result = self.build([hand(1, 0, 10, allowed=False)])
        self.assertFalse(result["hands"][0]["conditional_analysis_allowed"])
        self.assertFalse(result["hands"][0]["evidence_gate_allowed"])
        self.assertEqual(result["hands"][0]["status"], "INSUFFICIENT_DATA")

    def test_invalid_duration_raises(self):
        for duration in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    self.build([hand(1, 0, 10)], duration=duration)


if __name__ == "__main__":
    unittest.main()
