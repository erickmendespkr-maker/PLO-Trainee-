"""Regression tests for OCR board order and actual board transitions."""
import unittest

from video_analyzer.offline_hand_timeline import Observation, propose_intervals


class BoardOrderTests(unittest.TestCase):
    def test_permutation_is_not_new_board(self):
        observations = [
            Observation("table-1", 1, "flop", ("As", "Kd", "2c"), 0.9),
            Observation("table-1", 2, "flop", ("2C", " AS ", "kd"), 0.8),
        ]
        self.assertEqual(propose_intervals(observations, 10), [])

    def test_replacement_still_proposes_review(self):
        observations = [
            Observation("table-1", 1, "flop", ("As", "Kd", "2c"), 0.9),
            Observation("table-1", 2, "flop", ("As", "Kd", "3c"), 0.8),
        ]
        result = propose_intervals(observations, 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["reason"], "board_change")
        self.assertFalse(result[0]["verified_by_human"])
        self.assertFalse(result[0]["boundary_exact"])

    def test_street_reset_remains_candidate_even_same_board(self):
        observations = [
            Observation("table-1", 1, "river", ("As", "Kd", "2c", "4h", "5s"), 0.9),
            Observation("table-1", 2, "turn", ("5s", "4h", "2c", "Kd", "As"), 0.8),
        ]
        result = propose_intervals(observations, 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["reason"], "street_reset")


if __name__ == "__main__":
    unittest.main()
