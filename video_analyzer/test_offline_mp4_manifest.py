import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_mp4_manifest import manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=10:d=1', '-c:v', 'mpeg4', '-y', str(self.path)], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_ffmpeg_clip_manifest(self):
        result = manifest(self.path, 10, 11, 'a'*64, 2)
        self.assertEqual(result['clip_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual((result['width'], result['height']), (160, 90))
        self.assertEqual(result['analysis_status'], 'INSUFFICIENT_DATA')
        self.assertFalse(result['hand_reconstruction_verified'])
        self.assertAlmostEqual(result['clip_duration_seconds'], 1, places=1)

    def test_reject_invalid_inputs(self):
        for start, end, sha, table in [(2, 1, 'a'*64, 1), (0, 1, 'x'*64, 1), (0, 1, 'a'*64, 5), (float('nan'), 1, 'a'*64, 1)]:
            with self.subTest(start=start, end=end, table=table):
                with self.assertRaises(ValueError):
                    manifest(self.path, start, end, sha, table)

    def test_reject_nonvideo(self):
        bogus = Path(self.temp.name) / 'bogus.txt'
        bogus.write_text('not video')
        with self.assertRaises(ValueError):
            manifest(bogus, 0, 1, 'a'*64, 1)


if __name__ == '__main__':
    unittest.main()
