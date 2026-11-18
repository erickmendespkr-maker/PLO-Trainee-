import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from offline_reviewed_clip_executor import export_reviewed_clip


def plan(source):
    obj = {'status': 'READY_FOR_OFFLINE_EXPORT', 'hand_id': 'synthetic-1', 'table_id': 1,
           'start_pts': 0.25, 'end_pts': 1.25,
           'video_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'explanation': 'Conditional model, not GTO', 'conditional_model_only': True,
           'not_gto': True, 'requires_source_hash_check': True}
    obj['manifest_sha256'] = hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return obj


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        if shutil.which('ffmpeg'):
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=320x240:rate=15', '-t', '2', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(self.source)], check=True)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg unavailable')
    def test_export_and_provenance(self):
        p = plan(self.source)
        out = self.root / 'out.mp4'
        meta = export_reviewed_clip(self.source, p, out)
        self.assertTrue(out.is_file())
        self.assertEqual(meta['clip_sha256'], hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertEqual(json.loads(Path(str(out)+'.json').read_text()), meta)
        self.assertEqual(meta['reviewed_explanation'], p['explanation'])
        self.assertAlmostEqual(meta['clip_duration_seconds'], 1, delta=.15)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg unavailable')
    def test_reject_tampered_plan(self):
        p = plan(self.source)
        p['start_pts'] = 0.5
        with self.assertRaisesRegex(ValueError, 'modified clip plan'):
            export_reviewed_clip(self.source, p, self.root/'out.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg unavailable')
    def test_reject_wrong_video(self):
        p = plan(self.source)
        p['video_sha256'] = '0'*64
        p['manifest_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='manifest_sha256'}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            export_reviewed_clip(self.source, p, self.root/'out.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg unavailable')
    def test_reject_unreviewed(self):
        p = plan(self.source)
        p['status'] = 'REVIEW_REQUIRED'
        with self.assertRaisesRegex(ValueError, 'human-reviewed'):
            export_reviewed_clip(self.source, p, self.root/'out.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg unavailable')
    def test_no_overwrite(self):
        p = plan(self.source)
        out = self.root / 'out.mp4'
        out.write_bytes(b'existing')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            export_reviewed_clip(self.source, p, out)
        self.assertEqual(out.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
