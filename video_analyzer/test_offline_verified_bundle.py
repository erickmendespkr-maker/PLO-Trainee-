import unittest
from unittest.mock import patch
try:
    from . import offline_verified_bundle as mod
except ImportError:
    import offline_verified_bundle as mod


class VerifiedBundleTests(unittest.TestCase):
    def test_integrity_success(self):
        with patch.object(mod, 'export_review_bundle', return_value={
            'clip': 'a.mp4', 'report': 'a.json'}) as export, patch.object(
                mod, 'verify_bundle', return_value={
                    'status': 'INTEGRITY_OK_TEMPORAL_ONLY',
                    'problems': [], 'visual_verification': False}) as audit:
            result = mod.export_and_verify_bundle('source.mp4', 'a.mp4', {},
                clip_start_s=1, clip_end_s=3)
        self.assertEqual(result['status'], 'EXPORTED_INTEGRITY_OK_TEMPORAL_ONLY')
        self.assertFalse(result['strategic_verification'])
        export.assert_called_once()
        audit.assert_called_once_with('a.mp4', ffprobe='ffprobe', tolerance_s=0.25)

    def test_integrity_failure_not_promoted(self):
        with patch.object(mod, 'export_review_bundle', return_value={
            'clip': 'a.mp4', 'report': 'a.json'}), patch.object(
                mod, 'verify_bundle', return_value={
                    'status': 'INVALID', 'problems': ['clip_hash_mismatch'],
                    'visual_verification': False}):
            result = mod.export_and_verify_bundle('source.mp4', 'a.mp4', {},
                clip_start_s=1, clip_end_s=3)
        self.assertEqual(result['status'], 'EXPORTED_INTEGRITY_FAILED')
        self.assertEqual(result['audit']['problems'], ['clip_hash_mismatch'])
        self.assertFalse(result['visual_verification'])

    def test_export_failure_propagates(self):
        with patch.object(mod, 'export_review_bundle', side_effect=ValueError('bad')):
            with patch.object(mod, 'verify_bundle') as audit:
                with self.assertRaises(ValueError):
                    mod.export_and_verify_bundle('s', 'c', {}, clip_start_s=1, clip_end_s=2)
                audit.assert_not_called()

    def test_audit_failure_propagates_without_false_success(self):
        with patch.object(mod, 'export_review_bundle', return_value={
            'clip': 'a.mp4', 'report': 'a.json'}), patch.object(
                mod, 'verify_bundle', side_effect=OSError('probe')):
            with self.assertRaises(OSError):
                mod.export_and_verify_bundle('s', 'c', {}, clip_start_s=1, clip_end_s=2)


if __name__ == '__main__':
    unittest.main()
