"""Synthetic offline clip/review binding tests; requires FFmpeg and FFprobe."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_review_binding import audit_against_review


class ReviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'clip.mp4'
        self.record = dict(source_sha256='a'*64, hand_id='h-1', table_id=1,
                           start_seconds=0.0, end_seconds=1.0,
                           review_status='insufficient_data')

    @patch('offline_review_binding.audit_export')
    def test_forwards_every_trusted_field(self, audit):
        audit.return_value = {'integrity_verified': True}
        result = audit_against_review(self.path, self.record)
        self.assertEqual(audit.call_args.kwargs['expected_interval'], (0.0, 1.0))
        self.assertEqual(audit.call_args.kwargs['expected_review_status'], 'insufficient_data')
        self.assertTrue(result['trusted_review_binding_verified'])
        self.assertFalse(result['strategic_error_established'])

    @patch('offline_review_binding.audit_export')
    def test_missing_field_fails_closed(self, audit):
        del self.record['hand_id']
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            audit_against_review(self.path, self.record)
        audit.assert_not_called()

    @patch('offline_review_binding.audit_export')
    def test_bad_hash_fails_closed(self, audit):
        self.record['source_sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'source hash'):
            audit_against_review(self.path, self.record)
        audit.assert_not_called()

    @patch('offline_review_binding.audit_export')
    def test_invalid_status_fails_closed(self, audit):
        self.record['review_status'] = 'gto'
        with self.assertRaisesRegex(ValueError, 'review status'):
            audit_against_review(self.path, self.record)
        audit.assert_not_called()

    @patch('offline_review_binding.audit_export')
    def test_audit_mismatch_propagates(self, audit):
        audit.side_effect = ValueError('hand identity mismatch')
        with self.assertRaisesRegex(ValueError, 'hand identity mismatch'):
            audit_against_review(self.path, self.record)


if __name__ == '__main__':
    unittest.main()
