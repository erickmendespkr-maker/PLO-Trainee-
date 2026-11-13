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


if __name__ == '__main__':
    unittest.main()
