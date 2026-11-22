"""Real FFmpeg regression checks for safe offline MP4 export (synthetic input)."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .offline_ffmpeg_clip_export import export_review_clip
except ImportError:
    from offline_ffmpeg_clip_export import export_review_clip

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe unavailable')
class RealFFmpegFailurePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mp4'
        self.output = self.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x90:rate=10:duration=3', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', str(self.source)], check=True)

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_real_export_decodes_and_preserves_source(self):
        original = self.digest(self.source)
        result = export_review_clip(self.source, self.output, start_s=0.5, end_s=1.5)
        self.assertEqual(result['status'], 'EXPORTED_TEMPORAL_ONLY')
        self.assertFalse(result['visually_verified'])
        self.assertAlmostEqual(result['actual_duration_s'], 1.0, delta=0.25)
        self.assertEqual(self.digest(self.source), original)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(self.output),
                        '-f', 'null', '-'], check=True)
        self.assertFalse((self.root / 'clip.partial.mp4').exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b'other-job')
        with self.assertRaises(FileExistsError):
            export_review_clip(self.source, self.output, start_s=0, end_s=1)
        self.assertEqual(self.output.read_bytes(), b'other-job')

    def test_existing_partial_is_preserved(self):
        partial = self.root / 'clip.partial.mp4'
        partial.write_bytes(b'other-job')
        with self.assertRaises(FileExistsError):
            export_review_clip(self.source, self.output, start_s=0, end_s=1)
        self.assertEqual(partial.read_bytes(), b'other-job')
        self.assertFalse(self.output.exists())

    def test_out_of_bounds_leaves_no_files(self):
        with self.assertRaises(ValueError):
            export_review_clip(self.source, self.output, start_s=2, end_s=4)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / 'clip.partial.mp4').exists())

    def test_bad_encoder_executable_leaves_no_files(self):
        with self.assertRaises(FileNotFoundError):
            export_review_clip(self.source, self.output, start_s=0, end_s=1,
                               ffmpeg='__missing_ffmpeg_binary_for_test__')
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / 'clip.partial.mp4').exists())

    def test_invalid_bounds_leave_source_unchanged(self):
        original = self.digest(self.source)
        for start, end in [(float('nan'), 1), (True, 1), (-1, 1), (1, 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                export_review_clip(self.source, self.output, start_s=start, end_s=end)
        self.assertEqual(self.digest(self.source), original)
        self.assertFalse(self.output.exists())

if __name__ == '__main__':
    unittest.main()
