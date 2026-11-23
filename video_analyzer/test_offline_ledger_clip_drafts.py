"""Synthetic tests for review-only clip window drafts."""
import copy
import unittest

try:
    from .offline_ledger_clip_drafts import draft_clip_windows
except ImportError:
    from offline_ledger_clip_drafts import draft_clip_windows


class LedgerClipDraftTests(unittest.TestCase):
    def test_padding_clamped_and_not_verified(self):
        result = draft_clip_windows({"hands": [{"table_id": 1, "start_s": 1, "end_s": 9}]}, duration_s=10)
        clip = result["clips"][0]
        self.assertEqual((clip["start_s"], clip["end_s"]), (0, 10))
        self.assertFalse(result["exported"])
        self.assertFalse(clip["hand_boundaries_verified"])

    def test_four_parallel_tables(self):
        hands = [{"table_id": i, "start_s": 10, "end_s": 20} for i in range(1, 5)]
        result = draft_clip_windows({"hands": hands}, duration_s=60)
        self.assertEqual([x["table_id"] for x in result["clips"]], [1, 2, 3, 4])

    def test_invalid_intervals_require_review(self):
        for start, end in [(5, 5), (-1, 3), (1, 101), (float("nan"), 4), (True, 5)]:
            with self.subTest(start=start, end=end):
                result = draft_clip_windows({"hands": [{"start_s": start, "end_s": end}]}, duration_s=100)
                self.assertEqual(result["clips"][0]["status"], "REVIEW_REQUIRED")

    def test_timeline_warning_preserved_without_mutation(self):
        ledger = {"hands": [{"start_s": 4, "end_s": 7, "timeline_issue_codes": ["SAME_TABLE_OVERLAP"]}]}
        original = copy.deepcopy(ledger)
        result = draft_clip_windows(ledger, duration_s=20)
        self.assertEqual(ledger, original)
        self.assertEqual(result["clips"][0]["reason"], "TIMELINE_ISSUES")

    def test_invalid_parameters(self):
        for duration in (0, -1, float("inf"), True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                draft_clip_windows({"hands": []}, duration_s=duration)
        with self.assertRaises(ValueError):
            draft_clip_windows({"hands": []}, duration_s=20, padding_s=-1)


if __name__ == "__main__":
    unittest.main()
