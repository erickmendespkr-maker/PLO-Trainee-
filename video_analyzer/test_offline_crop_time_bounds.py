import unittest
from offline_crop_time_bounds import validate_source_interval, has_frame_inside_interval


class TimeBoundsTests(unittest.TestCase):
    def test_valid_middle(self):
        self.assertEqual(validate_source_interval(50, 20, 100), (50, 70))

    def test_valid_tail_with_tolerance(self):
        self.assertEqual(validate_source_interval(99, 1.1, 100), (99, 100))

    def test_reject_after_eof(self):
        for args in [(100, 1, 100), (99, 2, 100), (-1, 1, 100), (0, 0, 100), (0, 301, 500)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_source_interval(*args)

    def test_reject_nan_bool_and_bad_tolerance(self):
        for args in [(float('nan'), 1, 100), (True, 1, 100), (0, 1, 100, 3)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_source_interval(*args)

    def test_nearby_keyframe_not_evidence(self):
        self.assertFalse(has_frame_inside_interval([9.7, 12.2], 10, 2, 100))

    def test_actual_frame_evidence(self):
        self.assertTrue(has_frame_inside_interval([9.7, 10.1], 10, 2, 100))

    def test_nonfinite_pts_ignored(self):
        self.assertFalse(has_frame_inside_interval([float('nan'), None, '10.5'], 10, 2, 100))

    def test_eof_cannot_be_bypassed_by_frame(self):
        with self.assertRaises(ValueError):
            has_frame_inside_interval([99.9], 99, 2, 100)


if __name__ == '__main__':
    unittest.main()
