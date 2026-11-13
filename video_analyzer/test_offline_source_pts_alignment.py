import unittest
from offline_source_pts_alignment import compare_frame_timelines as compare


class TimelineTests(unittest.TestCase):
    def test_matching(self):
        result = compare([10, 10.1, 10.2, 10.3], [0, 0.1, 0.2, 0.3], 10, 10.4)
        self.assertEqual(result['status'], 'FRAME_TIMING_CANDIDATE_ONLY')
        self.assertIs(result['approved_for_publication'], False)
        self.assertIs(result['source_timeline_verified'], False)

    def test_gap(self):
        with self.assertRaises(ValueError):
            compare([10, 10.1, 10.4], [0, 0.1, 0.2], 10, 10.5)

    def test_clip_overrun(self):
        with self.assertRaises(ValueError):
            compare([10, 10.1, 10.2], [0, 0.1, 0.6], 10, 10.3)

    def test_duplicates(self):
        with self.assertRaises(ValueError):
            compare([10, 10, 10.2], [0, 0.1], 10, 10.3)

    def test_nan(self):
        with self.assertRaises(ValueError):
            compare([10, float('nan')], [0, 0.1], 10, 10.3)

    def test_boolean(self):
        with self.assertRaises(ValueError):
            compare([10, True], [0, 0.1], 10, 10.3)

    def test_empty(self):
        with self.assertRaises(ValueError):
            compare([], [0], 10, 11)

    def test_bad_tolerance(self):
        with self.assertRaises(ValueError):
            compare([10], [0], 10, 11, tolerance_seconds=0.5)

    def test_shifted_clip_pts(self):
        result = compare([10, 10.1, 10.2], [3, 3.1, 3.2], 10, 10.3)
        self.assertEqual(result['clip_frame_count'], 3)


if __name__ == '__main__':
    unittest.main()
