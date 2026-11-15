"""Synthetic tests for the offline artifact audit contract."""
import unittest
try:
    from .offline_audit_contract import validate_audit_result
except ImportError:
    from offline_audit_contract import validate_audit_result

H = 'a' * 64

def audit():
    return {'verified_artifacts': True, 'strategic_verdict_allowed': False,
            'human_review_required': True, 'clip_sha256': H,
            'duration_seconds': 2.0}

class AuditContractTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_audit_result(audit(), H)['clip_sha256'], H)
    def test_no_exporter_hash(self):
        self.assertEqual(validate_audit_result(audit())['duration_seconds'], 2.0)
    def test_wrong_exporter_hash(self):
        with self.assertRaises(ValueError): validate_audit_result(audit(), 'b'*64)
    def test_malformed_exporter_hash(self):
        with self.assertRaises(ValueError): validate_audit_result(audit(), 'abc')
    def test_malformed_audit_hash(self):
        x=audit(); x['clip_sha256']='x'*64
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_nonfinite_duration(self):
        x=audit(); x['duration_seconds']=float('nan')
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_zero_duration(self):
        x=audit(); x['duration_seconds']=0
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_boolean_duration(self):
        x=audit(); x['duration_seconds']=True
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_unsafe_verdict(self):
        x=audit(); x['strategic_verdict_allowed']=True
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_unreviewed(self):
        x=audit(); x['human_review_required']=False
        with self.assertRaises(ValueError): validate_audit_result(x)
    def test_not_dict(self):
        with self.assertRaises(ValueError): validate_audit_result(None)

if __name__ == '__main__':
    unittest.main()
