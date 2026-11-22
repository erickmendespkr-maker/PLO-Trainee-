"""Synthetic regression tests for read-only MP4 sidecar integrity."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .offline_bundle_integrity import verify_bundle
except ImportError:
    from offline_bundle_integrity import verify_bundle


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clip = Path(self.tmp.name) / 'clip.mp4'
        self.clip.write_bytes(b'fake-video')
        self.report = self.clip.with_suffix('.json')
        self.report.write_text(json.dumps({'clip': {'sha256': hashlib.sha256(b'fake-video').hexdigest(), 'actual_duration_s': 1.0}}))

    def probe(self):
        return patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"format":{"duration":"1.0"}}', ''))

    def test_valid(self):
        with self.probe():
            self.assertEqual(verify_bundle(self.clip)['status'], 'INTEGRITY_OK_TEMPORAL_ONLY')

    def test_mutation(self):
        self.clip.write_bytes(b'changed')
        with self.probe():
            self.assertIn('clip_hash_mismatch', verify_bundle(self.clip)['problems'])

    def test_missing(self):
        self.report.unlink()
        self.assertEqual(verify_bundle(self.clip)['status'], 'INVALID')

    def test_bad_json(self):
        self.report.write_text('{')
        self.assertIn('invalid_json', verify_bundle(self.clip)['problems'])

    def test_duration(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"format":{"duration":"2.0"}}', '')):
            self.assertIn('duration_mismatch', verify_bundle(self.clip)['problems'])

    def test_probe_failure(self):
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            self.assertIn('ffprobe_failed', verify_bundle(self.clip)['problems'])

    def test_tolerance_validation(self):
        for value in (-1, float('nan'), True):
            with self.assertRaises(ValueError):
                verify_bundle(self.clip, tolerance_s=value)

    def test_no_visual_claim(self):
        with self.probe():
            self.assertIs(verify_bundle(self.clip)['visual_verification'], False)


if __name__ == '__main__':
    unittest.main()
