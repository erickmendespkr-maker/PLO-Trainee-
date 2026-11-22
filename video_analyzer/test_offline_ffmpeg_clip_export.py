import tempfile
import subprocess
import unittest
from pathlib import Path

try:
    from video_analyzer.offline_ffmpeg_clip_export import export_review_clip
except ImportError:
    from offline_ffmpeg_clip_export import export_review_clip


class TestExport(unittest.TestCase):
    def test_real_ffmpeg(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'input.mp4'
            out = Path(d) / 'clip.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x90:rate=20', '-t', '3', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(src)], check=True)
            result = export_review_clip(src, out, start_s=.5, end_s=2.5)
            self.assertTrue(out.is_file())
            self.assertAlmostEqual(result['actual_duration_s'], 2, delta=.25)
            self.assertFalse(result['visually_verified'])

    def test_reject_bounds(self):
        for start, end in [(2, 1), (0, 0), (float('nan'), 1), (True, 2)]:
            with self.assertRaises(ValueError):
                export_review_clip('missing.mp4', 'out.mp4', start_s=start, end_s=end)

    def test_reject_missing_source(self):
        with self.assertRaises(ValueError):
            export_review_clip('missing.mp4', 'out.mp4', start_s=0, end_s=1)

    def test_reject_beyond_duration_and_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'input.mp4'
            out = Path(d) / 'clip.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=160x90:r=20', '-t', '1', '-c:v', 'libx264',
                            str(src)], check=True)
            with self.assertRaises(ValueError):
                export_review_clip(src, out, start_s=0, end_s=2)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
