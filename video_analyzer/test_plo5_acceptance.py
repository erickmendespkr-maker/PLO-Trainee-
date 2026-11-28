import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from plo5_acceptance import audit
from plo5_integrated_video import run

BANK=Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json'

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and BANK.exists(),'FFmpeg and bank required')
class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.video=cls.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(cls.video)],check=True,timeout=30)
        cls.report=cls.root/'report';run(cls.video,cls.report,ppp=BANK,chunk=2,workers=1,refine_budget=0)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def mutate(self,relative,fn):
        p=self.report/relative;raw=p.read_bytes();v=json.loads(raw);fn(v);p.write_text(json.dumps(v));self.addCleanup(p.write_bytes,raw)
    def test_valid_candidate_never_released(self):
        r=audit(self.video,self.report);self.assertTrue(r['structural_audit_passed']);self.assertFalse(r['beta_ready']);self.assertEqual(r['windows'],2);self.assertEqual(r['counts']['decoded_frames'],4)
    def test_reject_false_readiness(self):
        self.mutate('summary.json',lambda x:x.update(beta_ready=True))
        with self.assertRaisesRegex(ValueError,'readiness'):audit(self.video,self.report)
    def test_reject_window_count(self):
        self.mutate('summary.json',lambda x:x['windows'][0].update(decoded_frames=99))
        with self.assertRaisesRegex(ValueError,'Window count'):audit(self.video,self.report)
    def test_reject_capture_error(self):
        self.mutate('window_00001/capture/manifest.json',lambda x:x.update(errors=[{'fake':True}]))
        with self.assertRaisesRegex(ValueError,'Capture selection'):audit(self.video,self.report)
    def test_reject_unexpected_print(self):
        p=self.report/'window_00001/study/prints/extra.png';p.write_bytes(b'fake');self.addCleanup(p.unlink)
        with self.assertRaisesRegex(ValueError,'Unexpected print'):audit(self.video,self.report)
    def test_reject_source_mismatch(self):
        p=self.root/'other.mp4';p.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError,'Source or report'):audit(p,self.report)

if __name__=='__main__':unittest.main()
