"""Regression tests for OCR formatting in offline hand timeline."""
import unittest
from offline_hand_timeline import Observation, propose_intervals


class BoardNormalizationTests(unittest.TestCase):
    def test_case_and_whitespace_do_not_create_false_boundary(self):
        observations = [Observation("1", 1, "flop", ("As", "Kd", "Qh"), .9),
                        Observation("1", 2, "flop", (" as ", "KD", " qH "), .8)]
        self.assertEqual(propose_intervals(observations, 10), [])

    def test_actual_board_change_remains_review_only(self):
        observations = [Observation("1", 1, "flop", ("As", "Kd", "Qh"), .9),
                        Observation("1", 2, "turn", ("AS", "KD", "QH", "2c"), .8)]
        output = propose_intervals(observations, 10)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["reason"], "board_change")
        self.assertFalse(output[0]["verified_by_human"])
        self.assertFalse(output[0]["boundary_exact"])

    def test_street_reset_still_proposed_when_board_formats_differ(self):
        observations = [Observation("1", 1, "river", ("As", "Kd", "Qh", "2c", "3s"), .9),
                        Observation("1", 2, "preflop", (), .8)]
        self.assertEqual(propose_intervals(observations, 10)[0]["reason"], "street_reset")


if __name__ == "__main__":
    unittest.main()
