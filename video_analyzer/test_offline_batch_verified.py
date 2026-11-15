"""Synthetic contract tests for offline batch verification."""
import unittest
from unittest.mock import patch
try:
    from .offline_batch_verified import execute_and_audit
except ImportError:
    from offline_batch_verified import execute_and_audit

def batch(status='EXPORTED_UNREVIEWED', count=1):
    return {'results': [{'destination': '/tmp/clip.mp4', 'status': status,
                         'clip_sha256': 'a'*64} for _ in range(count)],
            'planned_count': count, 'attempted_count': count}

def verified(**changes):
    return {**{'verified_artifacts': True, 'human_review_required': True,
               'strategic_verdict_allowed': False, 'clip_sha256': 'a'*64,
               'duration_seconds': 2.0}, **changes}

class VerifiedBatchTests(unittest.TestCase):
    def invoke(self, payload, audit):
        with patch.dict(execute_and_audit.__globals__, {'execute_review_batch': lambda *a, **k: payload}):
            return execute_and_audit('source', [], 3, '/tmp', auditor=audit)

    def test_success(self):
        r = self.invoke(batch(), lambda _: verified())
        self.assertEqual(r['verified_count'], 1)
        self.assertEqual(r['status'], 'ARTIFACTS_VERIFIED_UNREVIEWED')
        self.assertFalse(r['results'][0]['strategic_verdict_allowed'])

    def test_hash_mismatch(self):
        r = self.invoke(batch(), lambda _: {**verified(), 'clip_sha256': 'b'*64})
        self.assertEqual(r['results'][0]['status'], 'AUDIT_FAILED_UNREVIEWED')

    def test_unsafe_verdict(self):
        r = self.invoke(batch(), lambda _: {**verified(), 'strategic_verdict_allowed': True})
        self.assertEqual(r['verified_count'], 0)

    def test_exception(self):
        def fail(_):
            raise ValueError('corrupt')
        self.assertEqual(self.invoke(batch(), fail)['status'], 'PARTIAL_OR_FAILED')

    def test_failed_export_skips_audit(self):
        def fail(_):
            raise AssertionError('should not audit')
        self.assertEqual(self.invoke(batch('FAILED'), fail)['verified_count'], 0)

    def test_empty(self):
        self.assertEqual(self.invoke(batch(count=0), lambda _: verified())['status'], 'PARTIAL_OR_FAILED')

if __name__ == '__main__':
    unittest.main()
