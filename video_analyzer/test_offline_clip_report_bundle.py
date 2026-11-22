"""Regression tests for conservative clip-to-report binding."""
import unittest
try:
    from .offline_clip_report_bundle import build_clip_report_bundle
except ImportError:
    from offline_clip_report_bundle import build_clip_report_bundle

SHA = 'a' * 64
READY = {'status': 'CONDITIONAL_EV_ONLY', 'start_s': 10, 'end_s': 20,
         'evidence': {'status': 'READY_FOR_CONDITIONAL_ANALYSIS'},
         'scenario_id': 'range-a',
         'conditional_ev': {'ev_low_chips': -5, 'ev_high_chips': 25}}


class BundleTests(unittest.TestCase):
    def bundle(self, analysis=READY, **kw):
        return build_clip_report_bundle(
            analysis, video_sha256=SHA,
            clip_start_s=kw.pop('clip_start_s', 9),
            clip_end_s=kw.pop('clip_end_s', 21),
            video_duration_s=30, **kw)

    def test_aligned_conditional(self):
        result = self.bundle()
        self.assertEqual(result['report']['status'], 'CONDITIONAL_EV_ONLY')
        self.assertFalse(result['report']['clip']['visually_verified'])
        self.assertIsNone(result['report']['strategic_conclusion'])

    def test_truncated_clip_suppresses_ev(self):
        result = self.bundle(clip_start_s=11)
        self.assertEqual(result['report']['status'], 'INSUFFICIENT_DATA')
        self.assertIsNone(result['report']['conditional_ev'])
        self.assertEqual(result['alignment']['reason'], 'CLIP_DOES_NOT_COVER_HAND')

    def test_missing_hand_timestamps(self):
        result = self.bundle({'status': 'CONDITIONAL_EV_ONLY', 'evidence': READY['evidence']})
        self.assertEqual(result['report']['status'], 'INSUFFICIENT_DATA')

    def test_unreviewed_evidence_not_upgraded(self):
        analysis = dict(READY, evidence={'status': 'INSUFFICIENT_DATA'})
        self.assertEqual(self.bundle(analysis)['report']['status'], 'INSUFFICIENT_DATA')

    def test_invalid_video_duration(self):
        with self.assertRaises(ValueError):
            build_clip_report_bundle(READY, video_sha256=SHA, clip_start_s=9,
                                     clip_end_s=21, video_duration_s=float('nan'))

    def test_invalid_hash(self):
        with self.assertRaises(ValueError):
            build_clip_report_bundle(READY, video_sha256='wrong', clip_start_s=9,
                                     clip_end_s=21, video_duration_s=30)

    def test_exact_boundaries(self):
        result = self.bundle(clip_start_s=10, clip_end_s=20)
        self.assertEqual(result['alignment']['status'], 'TEMPORALLY_ALIGNED_ONLY')

    def test_tolerance(self):
        result = self.bundle(clip_start_s=10.03, clip_end_s=19.97)
        self.assertEqual(result['alignment']['status'], 'TEMPORALLY_ALIGNED_ONLY')


if __name__ == '__main__':
    unittest.main()
