"""Regression tests for table identity in offline hand proposals."""
import unittest

from video_analyzer.offline_hand_timeline import Observation, propose_intervals


class TableIdentityTests(unittest.TestCase):
    def test_incidental_whitespace_does_not_split_a_table(self):
        observations = [
            Observation(" mesa-1 ", 1.0, "preflop", (), 0.9),
            Observation("mesa-1", 2.0, "flop", ("As", "Kd", "Qc"), 0.8),
        ]
        result = propose_intervals(observations, 5.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["table_id"], "mesa-1")
        self.assertFalse(result[0]["verified_by_human"])
        self.assertFalse(result[0]["boundary_exact"])

    def test_distinct_tables_remain_separate(self):
        observations = [
            Observation("mesa-1", 1.0, "preflop"),
            Observation("mesa-2", 1.0, "preflop"),
            Observation("mesa-1 ", 2.0, "flop", ("As", "Kd", "Qc")),
            Observation(" mesa-2", 2.0, "flop", ("Ah", "Kh", "Qh")),
        ]
        result = propose_intervals(observations, 5.0)
        self.assertEqual({item["table_id"] for item in result}, {"mesa-1", "mesa-2"})
        self.assertEqual(len(result), 2)

    def test_duplicate_timestamp_cannot_hide_behind_whitespace(self):
        with self.assertRaises(ValueError):
            propose_intervals([
                Observation("mesa-1", 1.0, "preflop"),
                Observation(" mesa-1 ", 1.0, "flop", ("As", "Kd", "Qc")),
            ], 5.0)


if __name__ == "__main__":
    unittest.main()
