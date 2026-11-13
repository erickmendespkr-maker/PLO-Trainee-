"""Synthetic FFmpeg export -> sidecar -> audit integration tests."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_clip_export import export_clip
from offline_clip_audit import audit_export


class ExportAuditIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x120:rate=10', '-t', '3',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(self.source)],
                       check=True, capture_output=True, timeout=30)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.plan = dict(source_sha256=self.source_hash, output_name='hand_001.mp4',
                         start_seconds=0.5, end_seconds=2.5, duration_seconds=2.0,
                         table_id=1, hand_id='synthetic-001', review_status='insufficient_data',
                         strategic_verdict_allowed=False)
        self.out = self.root / 'clips'

    def export(self):
        return export_clip(self.source, self.out, self.plan)

    def test_export_and_audit(self):
        metadata = self.export()
        clip = self.out / 'hand_001.mp4'
        report = audit_export(clip, expected_source_sha256=self.source_hash)
        self.assertEqual(report['clip_sha256'], metadata['clip_sha256'])
        self.assertTrue(report['integrity_verified'])
        self.assertFalse(report['hand_reconstruction_verified'])
        self.assertFalse(report['strategic_error_established'])
        self.assertFalse(report['gto_solution'])
        self.assertEqual(json.loads(Path(str(clip) + '.json').read_text())['annotation'], 'INSUFFICIENT_DATA')

    def test_tampering_after_export_rejected(self):
        self.export()
        clip = self.out / 'hand_001.mp4'
        with clip.open('ab') as f:
            f.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'clip hash mismatch'):
            audit_export(clip)

    def test_source_hash_constraint(self):
        self.export()
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            audit_export(self.out / 'hand_001.mp4', expected_source_sha256='0' * 64)

    def test_reexport_cannot_overwrite(self):
        self.export()
        with self.assertRaises(FileExistsError):
            self.export()

    def test_invalid_table_is_detected_by_audit(self):
        self.plan['table_id'] = 5
        self.export()
        with self.assertRaisesRegex(ValueError, 'invalid table id'):
            audit_export(self.out / 'hand_001.mp4')


if __name__ == '__main__':
    unittest.main()
