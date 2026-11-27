import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from plo5_video_stream import scan

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg absent')
class StreamTests(unittest.TestCase):
    def test_synthetic_pts_and_candidates(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'black.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(p)],check=True,timeout=30)
            r=scan(p,0,3)
            self.assertEqual([x['pts'] for x in r['frames']],['0','1','2'])
            self.assertEqual(len({x['rgb_sha256'] for x in r['frames']}),1)
            self.assertTrue(all(x['file'].endswith('.rgb') for x in r['frames']))
            self.assertEqual(r['evidence']['samples'],12)
            self.assertEqual(r['evidence']['display_changes'],[])
            self.assertFalse(r['png_evidence_written']);self.assertFalse(r['strategy_authorized'])
            self.assertEqual(list(Path(t).iterdir()),[p])
    def test_invalid_window(self):
        for a,b in ((-1,3),(0,1),(0,121)):
            with self.assertRaises(ValueError):scan('absent.mp4',a,b)
        with self.assertRaises(ValueError):scan('absent.mp4',0,2)

if __name__=='__main__':unittest.main()
