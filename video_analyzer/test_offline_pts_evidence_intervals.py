"""Synthetic regressions for conservative offline PTS evidence intervals."""
import unittest
from offline_pts_evidence_intervals import propose_transition_windows

SHA = "a" * 64


def sample(table, pts, state):
    return {"table_id": table, "pts": pts, "state": state, "frame_sha256": SHA}


class TestOfflinePtsEvidenceIntervals(unittest.TestCase):
    def test_transition_is_uncertain(self):
        result = propose_transition_windows([sample("t1", 1, "none"), sample("t1", 4, "flop")])[0]
        self.assertEqual((result["earliest_pts"], result["latest_pts"]), (1, 4))
        self.assertFalse(result["usable_as_hand_boundary"])
        self.assertTrue(result["requires_review"])

    def test_no_transition(self):
        self.assertEqual(propose_transition_windows([sample("t1", 1, "flop"), sample("t1", 2, "flop")]), [])

    def test_multitable_isolation(self):
        result = propose_transition_windows([sample("t2", 1, "river"), sample("t1", 1, "none"),
                                              sample("t2", 2, "none"), sample("t1", 2, "flop")])
        self.assertEqual(len(result), 2)

    def test_sparse_gap(self):
        self.assertEqual(propose_transition_windows([sample("a", 1, "x"), sample("a", 100, "y")])[0]["status"],
                         "SPARSE_UNCERTAIN")

    def test_unsorted_input(self):
        self.assertEqual(propose_transition_windows([sample("a", 2, "y"), sample("a", 1, "x")])[0]["from_state"], "x")

    def test_reject_duplicate_timestamp(self):
        with self.assertRaises(ValueError):
            propose_transition_windows([sample("a", 1, "x"), sample("a", 1, "y")])

    def test_reject_bool_pts(self):
        with self.assertRaises(ValueError):
            propose_transition_windows([sample("a", True, "x")])

    def test_reject_bad_hash(self):
        with self.assertRaises(ValueError):
            propose_transition_windows([dict(sample("a", 1, "x"), frame_sha256="bad")])

    def test_reject_bad_gap(self):
        with self.assertRaises(ValueError):
            propose_transition_windows([], max_gap_seconds=float("nan"))

    def test_reject_invalid_observation(self):
        with self.assertRaises(ValueError):
            propose_transition_windows([None])


if __name__ == "__main__":
    unittest.main()
