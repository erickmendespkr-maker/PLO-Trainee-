"""Regression tests: offline MP4 exports must never overwrite user files."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_analyzer.offline_ffmpeg_clip_export import export_review_clip


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and FFprobe required')
class TestClipExportNoOverwrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x90:rate=10', '-t', '2',
                        '-c:v', 'libx264', str(self.source)], check=True)

    def test_existing_destination_preserved(self):
        dest = self.root / 'output.mp4'
        dest.write_bytes(b'USER DATA')
        with self.assertRaises(FileExistsError):
            export_review_clip(self.source, dest, start_s=0, end_s=1)
        self.assertEqual(dest.read_bytes(), b'USER DATA')

    def test_new_destination_decodes(self):
        dest = self.root / 'output.mp4'
        result = export_review_clip(self.source, dest, start_s=0.25, end_s=1.25)
        self.assertEqual(result['status'], 'EXPORTED_TEMPORAL_ONLY')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(dest),
                        '-f', 'null', '-'], check=True)
        self.assertTrue(dest.is_file())
        self.assertFalse((self.root / 'output.partial.mp4').exists())


if __name__ == '__main__':
    unittest.main()
