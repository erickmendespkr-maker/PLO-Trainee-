"""Regression: reject mismatched clip duration and symlink input."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_mp4_manifest import manifest


class ManifestDurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=10:d=1', '-c:v', 'mpeg4', '-y', str(self.path)], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_matching_duration_accepted(self):
        self.assertAlmostEqual(manifest(self.path, 10, 11, 'a'*64, 1)['clip_duration_seconds'], 1, places=1)

    def test_large_duration_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration does not match'):
            manifest(self.path, 10, 30, 'a'*64, 1)

    def test_small_duration_difference_within_codec_tolerance(self):
        self.assertEqual(manifest(self.path, 10, 11.2, 'a'*64, 1)['analysis_status'], 'INSUFFICIENT_DATA')

    def test_symlink_rejected(self):
        link = Path(self.temp.name) / 'link.mp4'
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            manifest(link, 10, 11, 'a'*64, 1)


if __name__ == '__main__':
    unittest.main()
