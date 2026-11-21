"""Regression tests for malformed offline timeline observations."""
import unittest
from video_analyzer.offline_hand_timeline import Observation, propose_intervals


class ObservationTypeValidationTests(unittest.TestCase):
    def test_rejects_non_observation_objects(self):
        for invalid in (None, {}, 3, "bad", (1, 2), object()):
            with self.subTest(value=repr(invalid)), self.assertRaisesRegex(ValueError, "observation must be an Observation"):
                propose_intervals([invalid], 10)

    def test_rejects_mixed_valid_and_invalid(self):
        with self.assertRaises(ValueError):
            propose_intervals([Observation("1", 1.0, "flop", ("As", "Kd", "Qc"), .9), None], 10)

    def test_valid_observations_preserve_provisional_semantics(self):
        rows = propose_intervals([
            Observation("1", 1.0, "flop", ("As", "Kd", "Qc"), .9),
            Observation("1", 2.0, "turn", ("As", "Kd", "Qc", "2h"), .7)
        ], 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["confidence_upper_bound"], .7)
        self.assertFalse(rows[0]["verified_by_human"])
        self.assertFalse(rows[0]["boundary_exact"])


if __name__ == "__main__":
    unittest.main()
