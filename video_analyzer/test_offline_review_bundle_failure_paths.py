"""Failure-path regression tests for offline clip + JSON handoff.

No poker decisions or real video required. Uses mocks to isolate filesystem
ownership behavior; the FFmpeg integration tests remain separate.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import offline_review_bundle_export as module
except ImportError:
    import offline_review_bundle_export as module


def _bundle():
    return {
        'alignment': {'status': 'TEMPORALLY_ALIGNED_ONLY'},
        'report': {'status': 'INSUFFICIENT_DATA', 'clip': {}},
    }


class ReviewBundleFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.mp4'
        self.source.write_bytes(b'synthetic-source')
        self.clip = Path(self.temp.name) / 'review.mp4'
        self.sidecar = self.clip.with_suffix('.json')

    def export(self):
        return module.export_review_bundle(
            self.source, self.clip,
            {'start_s': 0.2, 'end_s': 1.2, 'status': 'INSUFFICIENT_DATA'},
            clip_start_s=0.2, clip_end_s=1.2,
        )

    def fake_export(self, source, destination, **kwargs):
        Path(destination).write_bytes(b'synthetic-clip')
        return {'status': 'EXPORTED_TEMPORAL_ONLY', 'actual_duration_s': 1.0}

    def test_existing_sidecar_is_never_removed(self):
        self.sidecar.write_text('another-job', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.sidecar.read_text(encoding='utf-8'), 'another-job')
        self.assertFalse(self.clip.exists())

    def test_concurrent_sidecar_survives_and_owned_clip_is_cleaned(self):
        def competing_export(source, destination, **kwargs):
            self.fake_export(source, destination, **kwargs)
            self.sidecar.write_text('another-job', encoding='utf-8')
            return {'status': 'EXPORTED_TEMPORAL_ONLY', 'actual_duration_s': 1.0}

        with patch.object(module, '_duration', return_value=3.0), \
             patch.object(module, 'build_clip_report_bundle', return_value=_bundle()), \
             patch.object(module, 'export_review_clip', side_effect=competing_export):
            with self.assertRaises(FileExistsError):
                self.export()
        self.assertEqual(self.sidecar.read_text(encoding='utf-8'), 'another-job')
        self.assertFalse(self.clip.exists())

    def test_report_serialization_failure_cleans_owned_clip(self):
        bad = _bundle()
        bad['report']['not_serializable'] = object()
        with patch.object(module, '_duration', return_value=3.0), \
             patch.object(module, 'build_clip_report_bundle', return_value=bad), \
             patch.object(module, 'export_review_clip', side_effect=self.fake_export):
            with self.assertRaises(TypeError):
                self.export()
        self.assertFalse(self.clip.exists())
        self.assertFalse(self.sidecar.exists())

    def test_export_failure_does_not_delete_unowned_files(self):
        def failed_export(source, destination, **kwargs):
            raise RuntimeError('synthetic encoder failure')
        with patch.object(module, '_duration', return_value=3.0), \
             patch.object(module, 'build_clip_report_bundle', return_value=_bundle()), \
             patch.object(module, 'export_review_clip', side_effect=failed_export):
            with self.assertRaises(RuntimeError):
                self.export()
        self.assertTrue(self.source.exists())
        self.assertFalse(self.clip.exists())
        self.assertFalse(self.sidecar.exists())


if __name__ == '__main__':
    unittest.main()
