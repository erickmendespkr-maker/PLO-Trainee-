import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from plo5_video_preflight import scan


class VideoPreflightTests(unittest.TestCase):
    def test_rejects_invalid_sampling(self):
        for opts in ({'step_seconds':0}, {'max_samples':513},
                     {'ocr_samples':513}, {'max_samples':2,'ocr_samples':3}):
            with self.subTest(opts=opts):
                with self.assertRaisesRegex(ValueError, 'sampling budget'):
                    scan('missing.mp4', **opts)

    def test_requires_local_mp4(self):
        with self.assertRaisesRegex(ValueError, 'Local MP4'):
            scan('missing.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_black_video_reports_only_uncertainty(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t)/'black.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'color=c=black:s=1504x696:r=4','-t','3',
                            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],
                           check=True, timeout=30)
            result = scan(v,step_seconds=1,max_samples=10,ocr_samples=2)
            self.assertGreaterEqual(result['samples'],2)
            self.assertLessEqual(result['samples'],3)
            for row in result['layout_candidates'].values():
                self.assertEqual(row,{'undetected':result['samples']})
            self.assertEqual(result['ocr_availability'],{'stack':{},'pot':{}})
            self.assertFalse(result['hands_reconstructed'])
            self.assertFalse(result['financial_result_verified'])
            self.assertFalse(result['strategy_authorized'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_wrong_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            v=Path(t)/'tiny.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'color=c=black:s=320x240:r=2','-t','1',
                            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],
                           check=True,timeout=30)
            with self.assertRaisesRegex(ValueError,'Unsupported video'):
                scan(v)


if __name__=='__main__':unittest.main()
