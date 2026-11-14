"""Independent FFmpeg pixel-identity regression for four offline table crops.

Lossless FFV1 frames only. This is not poker hand or OCR verification.
"""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

REGIONS = [(0, 0), (64, 0), (0, 48), (64, 48)]


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=60).stdout


def rgb_frame(path, *, crop=None):
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
           '-i', str(path), '-frames:v', '1']
    if crop is not None:
        x, y = crop
        cmd += ['-vf', f'crop=64:48:{x}:{y}']
    cmd += ['-pix_fmt', 'rgb24', '-f', 'rawvideo', '-']
    return run(*cmd)


class FourTablePixelIdentity(unittest.TestCase):
    def test_lossless_four_table_pixels_match_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mkv'
            run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-f', 'lavfi', '-i', 'testsrc2=size=128x96:rate=10:duration=1',
                '-c:v', 'ffv1', str(source))
            for i, (x, y) in enumerate(REGIONS, 1):
                crop = root / f'table_{i}.mkv'
                run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                    '-i', str(source), '-vf', f'crop=64:48:{x}:{y}',
                    '-c:v', 'ffv1', str(crop))
                expected = rgb_frame(source, crop=(x, y))
                actual = rgb_frame(crop)
                self.assertEqual(len(expected), 64 * 48 * 3)
                self.assertEqual(hashlib.sha256(expected).digest(),
                                 hashlib.sha256(actual).digest(), f'table {i}')

    def test_wrong_region_does_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.mkv'
            run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-f', 'lavfi', '-i', 'testsrc2=size=128x96:rate=10:duration=1',
                '-c:v', 'ffv1', str(source))
            self.assertNotEqual(rgb_frame(source, crop=REGIONS[0]),
                                rgb_frame(source, crop=REGIONS[3]))


if __name__ == '__main__':
    unittest.main()
