import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from offline_clip_integrity import verify_export

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clip = Path(self.temp.name) / 'clip.mp4'
        self.clip.write_bytes(b'synthetic MP4 placeholder for integrity only')
        self.data = dict(schema_version=1, clip_sha256=hashlib.sha256(self.clip.read_bytes()).hexdigest(),
                         strategic_verdict_allowed=False, review_status='insufficient_data',
                         annotation='INSUFFICIENT_DATA', start_seconds=1, end_seconds=2,
                         actual_clip_duration_seconds=1)
        self.save()
    def save(self):
        Path(str(self.clip)+'.json').write_text(json.dumps(self.data))
    def test_valid(self):
        self.assertTrue(verify_export(self.clip)['verified'])
    def test_tamper(self):
        self.clip.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): verify_export(self.clip)
    def test_verdict(self):
        self.data['strategic_verdict_allowed'] = True; self.save()
        with self.assertRaises(ValueError): verify_export(self.clip)
    def test_annotation(self):
        self.data['annotation'] = 'BLUNDER'; self.save()
        with self.assertRaises(ValueError): verify_export(self.clip)
    def test_nonfinite(self):
        self.data['start_seconds'] = float('nan'); self.save()
        with self.assertRaises(ValueError): verify_export(self.clip)
    def test_duplicate_keys(self):
        Path(str(self.clip)+'.json').write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): verify_export(self.clip)
    def test_missing_sidecar(self):
        Path(str(self.clip)+'.json').unlink()
        with self.assertRaises(ValueError): verify_export(self.clip)

if __name__ == '__main__': unittest.main()
