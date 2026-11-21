"""Regression tests for offline review audit duration tolerance."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from video_analyzer.offline_review_export_audit import audit_review_export


class DurationAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clip = Path(self.tmp.name) / 'hand.mp4'
        self.clip.write_bytes(b'synthetic placeholder, ffprobe mocked')
        self.manifest = {
            'schema_version': 1,
            'clip_sha256': hashlib.sha256(self.clip.read_bytes()).hexdigest(),
            'source_duration_seconds': 60,
            'requested_interval_seconds': [10, 15],
            'table_id': 1,
            'ev_is_conditional': True,
            'gto_solution': False,
            'human_review_of_export': False,
            'evidence_gate': {
                'table_id': 1, 'start_pts': 10, 'end_pts': 15,
                'status': 'REVIEW_REQUIRED',
                'missing_evidence': ['hand_verified'],
                'can_label_error': False, 'can_attach_conditional_ev': False,
            },
        }
        self.clip.with_suffix('.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def check_duration(self, seconds):
        class Result:
            stdout = json.dumps({'streams': [{'codec_type': 'video'}],
                                 'format': {'duration': str(seconds)}})
        with patch('video_analyzer.offline_review_export_audit.subprocess.run', return_value=Result()):
            return audit_review_export(self.clip)

    def test_nominal_duration(self):
        self.assertTrue(self.check_duration(5)['integrity_verified'])

    def test_small_container_tolerance(self):
        self.assertTrue(self.check_duration(4.9)['integrity_verified'])

    def test_truncated_clip_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration mismatch'):
            self.check_duration(0.5)

    def test_oversized_clip_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration mismatch'):
            self.check_duration(5.5)

    def test_zero_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration mismatch'):
            self.check_duration(0)


if __name__ == '__main__':
    unittest.main()
