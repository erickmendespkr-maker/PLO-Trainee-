"""Duplicate visible board cards must not be accepted as valid evidence."""
import unittest
from video_analyzer.offline_hand_timeline import Observation, propose_intervals


class BoardIntegrityTests(unittest.TestCase):
    def test_duplicate_cards_rejected(self):
        for board in (
            ("As", "Kd", "AS"),
            ("Ah", "Kd", "Ah", "2s"),
            ("Ah", "Kd", "2s", "3c", "2s"),
            (" Ah ", "Kd", "AH"),
        ):
            with self.subTest(board=board), self.assertRaisesRegex(ValueError, "duplicate board cards"):
                propose_intervals([Observation("1", 1, "flop", board, 0.8)], 60)

    def test_distinct_board_cards_accepted(self):
        for street, board in (
            ("preflop", ()),
            ("flop", ("Ah", "Kd", "2s")),
            ("turn", ("Ah", "Kd", "2s", "3c")),
            ("river", ("Ah", "Kd", "2s", "3c", "4d")),
        ):
            with self.subTest(street=street):
                self.assertEqual(propose_intervals([Observation("1", 1, street, board, 0.8)], 60), [])

    def test_uncertain_ocr_is_not_promoted_to_verified_hand(self):
        rows = [
            Observation("1", 1, "flop", ("?", "Kd", "2s"), 0.3),
            Observation("1", 3, "turn", ("?", "Kd", "2s", "4h"), 0.4),
        ]
        result = propose_intervals(rows, 60)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence_upper_bound"], 0.3)
        self.assertFalse(result[0]["verified_by_human"])
        self.assertFalse(result[0]["boundary_exact"])


if __name__ == "__main__":
    unittest.main()
