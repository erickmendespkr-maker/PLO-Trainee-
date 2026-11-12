"""End-to-end synthetic test: reviewed clip gate -> FFmpeg MP4 + JSON."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_clip_export import export_clip, sha256_file
from offline_clip_plan_gate import plan_clip


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class ClipGateExportIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x90:rate=10', '-t', '3',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(self.source)],
                       check=True, timeout=30)

    def test_confirmed_conditional_clip(self):
        plan = plan_clip(sha256_file(self.source), 1, 'hand-1', .5, 2.0,
                         3.0, 'confirmed', 'hand-1.mp4')
        result = export_clip(self.source, self.root / 'out', plan)
        self.assertEqual(result['annotation'], 'CONDITIONAL MODEL ONLY')
        self.assertFalse(result['strategic_verdict_allowed'])
        output = self.root / 'out' / 'hand-1.mp4'
        self.assertTrue(output.is_file())
        self.assertEqual(sha256_file(output), result['clip_sha256'])
        self.assertEqual(json.loads((self.root / 'out' / 'hand-1.mp4.json').read_text()), result)

    def test_insufficient_data_not_promoted(self):
        plan = plan_clip(sha256_file(self.source), 4, 'hand-2', 0, 1,
                         3, 'insufficient_data', 'hand-2.mp4')
        result = export_clip(self.source, self.root / 'out', plan)
        self.assertEqual(result['annotation'], 'INSUFFICIENT_DATA')
        self.assertFalse(result['strategic_verdict_allowed'])

    def test_tampered_video_rejected(self):
        plan = plan_clip(sha256_file(self.source), 1, 'hand-3', 0, 1,
                         3, 'confirmed', 'hand-3.mp4')
        with self.source.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            export_clip(self.source, self.root / 'out', plan)


if __name__ == '__main__':
    unittest.main()
