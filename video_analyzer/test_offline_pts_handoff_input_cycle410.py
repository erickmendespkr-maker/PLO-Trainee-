"""Regression tests for sparse PTS handoff input validation (offline only)."""
import unittest

try:
    from .offline_pts_review_handoff import build_pts_review_handoff
except ImportError:
    from offline_pts_review_handoff import build_pts_review_handoff

VIDEO_SHA = "a" * 64
FRAME_SHA = "b" * 64


def observation(table="table-1", state="no-board", pts=0.0):
    return {"table_id": table, "state": state, "pts": pts, "frame_sha256": FRAME_SHA}


class HandoffInputRegressionTests(unittest.TestCase):
    def handoff(self, observations, **kwargs):
        return build_pts_review_handoff(
            observations, video_sha256=VIDEO_SHA,
            video_duration_seconds=60.0, **kwargs)

    def test_singleton_stays_pending_without_fabricated_hand(self):
        result = self.handoff([observation()])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["observed_tables"], 1)
        self.assertFalse(result["equity_or_ev_computed"])

    def test_rejects_blank_singleton_table(self):
        with self.assertRaises(ValueError):
            self.handoff([observation(table=" ")])

    def test_rejects_padded_singleton_table(self):
        with self.assertRaises(ValueError):
            self.handoff([observation(table=" table-1 ")])

    def test_rejects_blank_singleton_state(self):
        with self.assertRaises(ValueError):
            self.handoff([observation(state=" ")])

    def test_rejects_padded_singleton_state(self):
        with self.assertRaises(ValueError):
            self.handoff([observation(state=" flop ")])

    def test_rejects_invalid_max_tables_even_without_windows(self):
        for value in (0, 5, True, 1.5, "4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.handoff([], max_tables=value)

    def test_four_tables_allowed(self):
        rows = [observation(table=f"table-{i}") for i in range(4)]
        result = self.handoff(rows)
        self.assertEqual(result["observed_tables"], 4)
        self.assertEqual(result["tasks"], [])

    def test_fifth_table_rejected_without_windows(self):
        rows = [observation(table=f"table-{i}") for i in range(5)]
        with self.assertRaises(ValueError):
            self.handoff(rows)

    def test_changed_state_is_only_review_candidate(self):
        result = self.handoff([
            observation(pts=0, state="no-board"),
            observation(pts=10, state="flop"),
        ])
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["review_status"], "PENDING")
        self.assertFalse(result["tasks"][0]["strategic_commentary_allowed"])
        self.assertIsNone(result["tasks"][0]["verified_hand_id"])


if __name__ == "__main__":
    unittest.main()
