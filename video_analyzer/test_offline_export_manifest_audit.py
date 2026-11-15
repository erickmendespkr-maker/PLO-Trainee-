import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_export_manifest_audit import audit_export, _digest


class ManifestAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mp4 = Path(self.tmp.name) / 'clip.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=25:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(self.mp4)], check=True)
        self.data = dict(schema_version=1, clip_sha256=_digest(self.mp4), source_duration_seconds=10,
                         requested_interval_seconds=[1, 3], gto_solution=False,
                         human_review_of_export=False, ev_is_conditional=True,
                         explanation='No hand-specific mathematical conclusion is embedded in this clip.')
        self.save()
    def save(self):
        self.mp4.with_suffix('.json').write_text(json.dumps(self.data))
    def test_real_ffprobe(self):
        self.assertTrue(audit_export(self.mp4)['verified_artifacts'])
    def test_hash_tamper(self):
        self.mp4.write_bytes(self.mp4.read_bytes()+b'bad')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): audit_export(self.mp4)
    def test_duration_mismatch(self):
        self.data['requested_interval_seconds']=[1, 5]; self.save()
        with self.assertRaisesRegex(ValueError, 'duration mismatch'): audit_export(self.mp4)
    def test_false_review(self):
        self.data['human_review_of_export']=True; self.save()
        with self.assertRaises(ValueError): audit_export(self.mp4)
    def test_duplicate_json(self):
        self.mp4.with_suffix('.json').write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): audit_export(self.mp4)
    def test_missing_json(self):
        self.mp4.with_suffix('.json').unlink()
        with self.assertRaises(ValueError): audit_export(self.mp4)
    def test_bad_interval(self):
        self.data['requested_interval_seconds']=[3,1]; self.save()
        with self.assertRaises(ValueError): audit_export(self.mp4)

if __name__ == '__main__': unittest.main()
