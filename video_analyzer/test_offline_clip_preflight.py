"""Synthetic tests for offline clip preflight."""
import unittest
from offline_clip_preflight import validate_reviewed_interval

META = {"duration_seconds": 60.0, "width": 640, "height": 480}

class PreflightTests(unittest.TestCase):
    def test_valid(self):
        result = validate_reviewed_interval(META, 1, 3, (0, 0, 320, 240), True)
        self.assertFalse(result["equity_ev_verified"])
        self.assertTrue(result["human_reviewed_interval"])

    def test_review_required(self):
        with self.assertRaises(ValueError):
            validate_reviewed_interval(META, 1, 3)

    def test_nonfinite(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_reviewed_interval(META, value, 3, reviewed=True)

    def test_out_of_bounds(self):
        for start, end in ((-1, 2), (2, 2), (2, 61)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_reviewed_interval(META, start, end, reviewed=True)

    def test_crop_out_of_bounds(self):
        with self.assertRaises(ValueError):
            validate_reviewed_interval(META, 1, 3, (600, 0, 100, 100), True)

    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            validate_reviewed_interval(META, True, 3, reviewed=True)

if __name__ == "__main__":
    unittest.main()
