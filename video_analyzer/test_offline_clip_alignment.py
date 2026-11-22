import unittest
from offline_clip_alignment import audit_clip_alignment as audit

class ClipAlignmentTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(audit({'start_s': 5, 'end_s': 10}, clip_start_s=5, clip_end_s=10, video_duration_s=20)['status'], 'TEMPORALLY_ALIGNED_ONLY')
    def test_padding(self):
        self.assertEqual(audit({'start_s': 5, 'end_s': 10}, clip_start_s=4, clip_end_s=11, video_duration_s=20)['status'], 'TEMPORALLY_ALIGNED_ONLY')
    def test_truncated(self):
        self.assertEqual(audit({'start_s': 5, 'end_s': 10}, clip_start_s=6, clip_end_s=11, video_duration_s=20)['reason'], 'CLIP_DOES_NOT_COVER_HAND')
    def test_missing(self):
        self.assertEqual(audit({}, clip_start_s=1, clip_end_s=2, video_duration_s=20)['reason'], 'HAND_TIMESTAMPS_MISSING')
    def test_invalid_hand(self):
        self.assertEqual(audit({'start_s': 10, 'end_s': 5}, clip_start_s=1, clip_end_s=12, video_duration_s=20)['reason'], 'HAND_INTERVAL_INVALID')
    def test_bad_clip(self):
        with self.assertRaises(ValueError): audit({}, clip_start_s=0, clip_end_s=21, video_duration_s=20)
    def test_nan(self):
        with self.assertRaises(ValueError): audit({}, clip_start_s=float('nan'), clip_end_s=2, video_duration_s=20)
    def test_bool(self):
        with self.assertRaises(ValueError): audit({}, clip_start_s=True, clip_end_s=2, video_duration_s=20)
    def test_tolerance(self):
        self.assertEqual(audit({'start_s': 5, 'end_s': 10}, clip_start_s=5.03, clip_end_s=9.98, video_duration_s=20)['status'], 'TEMPORALLY_ALIGNED_ONLY')
    def test_not_visual(self):
        self.assertFalse(audit({'start_s': 5, 'end_s': 10}, clip_start_s=5, clip_end_s=10, video_duration_s=20)['visually_verified'])

if __name__ == '__main__': unittest.main()
