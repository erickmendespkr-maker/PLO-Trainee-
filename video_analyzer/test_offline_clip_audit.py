"""Synthetic FFmpeg tests of offline clip integrity."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_clip_audit import audit_export


class ClipAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mp4 = Path(self.tmp.name) / 'clip.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=128x96:r=10', '-t', '1', '-c:v', 'mpeg4', '-y', str(self.mp4)], check=True, capture_output=True, timeout=30)
        self.sidecar = Path(str(self.mp4) + '.json')
        self.metadata = {'schema_version': 1, 'source_sha256': 'a'*64,
                         'clip_sha256': hashlib.sha256(self.mp4.read_bytes()).hexdigest(),
                         'table_id': 1, 'start_seconds': 5, 'end_seconds': 6,
                         'actual_clip_duration_seconds': 1, 'review_status': 'insufficient_data',
                         'annotation': 'INSUFFICIENT_DATA', 'strategic_verdict_allowed': False}
        self.save()

    def save(self):
        self.sidecar.write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_valid_mp4_and_metadata(self):
        result = audit_export(self.mp4, expected_source_sha256='a'*64)
        self.assertTrue(result['integrity_verified'])
        self.assertFalse(result['hand_reconstruction_verified'])

    def test_modified_mp4_rejected(self):
        with self.mp4.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'clip hash mismatch'):
            audit_export(self.mp4)

    def test_modified_duration_rejected(self):
        self.metadata['end_seconds'] = 8
        self.save()
        with self.assertRaisesRegex(ValueError, 'sidecar interval mismatch'):
            audit_export(self.mp4)

    def test_modified_recorded_duration_rejected(self):
        self.metadata['end_seconds'] = 6.3
        self.metadata['actual_clip_duration_seconds'] = 1.3
        self.save()
        with self.assertRaisesRegex(ValueError, 'ffprobe duration mismatch'):
            audit_export(self.mp4)

    def test_unverified_annotation_rejected(self):
        self.metadata['annotation'] = 'BLUNDER'
        self.save()
        with self.assertRaisesRegex(ValueError, 'unverified annotation promoted'):
            audit_export(self.mp4)

    def test_source_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            audit_export(self.mp4, expected_source_sha256='b'*64)

    def test_symlink_rejected(self):
        alias = Path(self.tmp.name) / 'alias.mp4'
        alias.symlink_to(self.mp4)
        with self.assertRaisesRegex(ValueError, 'regular MP4 required'):
            audit_export(alias)

    def test_invalid_table_rejected(self):
        self.metadata['table_id'] = 5
        self.save()
        with self.assertRaisesRegex(ValueError, 'invalid table id'):
            audit_export(self.mp4)


if __name__ == '__main__':
    unittest.main()
