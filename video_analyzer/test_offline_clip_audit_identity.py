"""Regression tests for audited clip identity and conservative annotations."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_clip_export import export_clip, sha256_file
from offline_clip_audit import audit_export


class AuditIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'color=c=black:s=160x120:r=10', '-t', '2',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(self.source)],
                       check=True, capture_output=True, timeout=30)
        self.out = self.root / 'out'
        plan = dict(source_sha256=sha256_file(self.source), output_name='clip.mp4',
                    start_seconds=0.0, end_seconds=1.0, duration_seconds=1.0,
                    table_id=1, hand_id='hand-001', review_status='insufficient_data',
                    strategic_verdict_allowed=False)
        export_clip(self.source, self.out, plan)
        self.clip = self.out / 'clip.mp4'
        self.sidecar = Path(str(self.clip) + '.json')

    def modify(self, **changes):
        obj = json.loads(self.sidecar.read_text(encoding='utf-8'))
        obj.update(changes)
        self.sidecar.write_text(json.dumps(obj), encoding='utf-8')

    def test_valid_export(self):
        self.assertTrue(audit_export(self.clip)['integrity_verified'])

    def test_missing_hand_id_rejected(self):
        self.modify(hand_id=None)
        with self.assertRaisesRegex(ValueError, 'invalid hand id'):
            audit_export(self.clip)

    def test_malformed_hand_id_rejected(self):
        self.modify(hand_id='../unsafe')
        with self.assertRaisesRegex(ValueError, 'invalid hand id'):
            audit_export(self.clip)

    def test_confirmed_annotation_must_be_conditional(self):
        self.modify(review_status='confirmed', annotation='CERTAIN BLUNDER')
        with self.assertRaisesRegex(ValueError, 'annotation does not match review status'):
            audit_export(self.clip)

    def test_confirmed_conditional_annotation_allowed(self):
        self.modify(review_status='confirmed', annotation='CONDITIONAL MODEL ONLY')
        self.assertTrue(audit_export(self.clip)['integrity_verified'])

    def test_external_identity_matches(self):
        result = audit_export(self.clip, expected_hand_id='hand-001',
                              expected_table_id=1, expected_interval=(0.0, 1.0))
        self.assertTrue(result['integrity_verified'])

    def test_forged_hand_id_rejected_against_review_record(self):
        self.modify(hand_id='hand-999')
        with self.assertRaisesRegex(ValueError, 'hand identity mismatch'):
            audit_export(self.clip, expected_hand_id='hand-001')

    def test_forged_table_rejected_against_review_record(self):
        self.modify(table_id=2)
        with self.assertRaisesRegex(ValueError, 'table identity mismatch'):
            audit_export(self.clip, expected_table_id=1)

    def test_forged_interval_rejected_against_review_record(self):
        self.modify(start_seconds=0.1, end_seconds=1.1)
        with self.assertRaisesRegex(ValueError, 'source interval mismatch'):
            audit_export(self.clip, expected_interval=(0.0, 1.0))

    def test_invalid_external_interval_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source interval mismatch'):
            audit_export(self.clip, expected_interval=(True, 1.0))

    def test_trusted_review_status_matches(self):
        self.assertTrue(audit_export(self.clip, expected_review_status='insufficient_data')['integrity_verified'])

    def test_forged_review_promotion_rejected(self):
        self.modify(review_status='confirmed', annotation='CONDITIONAL MODEL ONLY')
        with self.assertRaisesRegex(ValueError, 'review status mismatch'):
            audit_export(self.clip, expected_review_status='insufficient_data')

    def test_invalid_expected_review_status_rejected(self):
        with self.assertRaisesRegex(ValueError, 'review status mismatch'):
            audit_export(self.clip, expected_review_status='unverified')


if __name__ == '__main__':
    unittest.main()
