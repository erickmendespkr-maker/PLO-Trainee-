import hashlib
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from PIL import Image
from plo5_card_refine import plan, choose_ticks, refine
from plo5_video_stream import scan
from test_plo5_error_prints import FixtureReader


def row(table,complete=False):
    return dict(table_id=table,platform='pppoker',hero_cards=['As','Ks','Qh','Jd','Tc'] if complete else None,board_cards=[],hero_slots=[dict(card='As')],board_slots=[],cards_verified=False)


def manifest():
    return dict(variant=5,source_sha256='a'*64,frames=[dict(pts='0',rgb_sha256='b'*64,cards=[row(1),row(2,True)]),dict(pts='2',rgb_sha256='c'*64,cards=[row(1,True)])])


class PlanTests(unittest.TestCase):
    def test_budget_and_unknowns(self):
        m=manifest();r=plan(m,0,3,2);self.assertEqual([(x['second'],x['tables']) for x in r],[(0,[1]),(1,[1,2,3,4])]);self.assertEqual(plan(m,0,3,1)[0]['second'],0)
        self.assertEqual(plan(dict(m,frames=[m['frames'][1]]),2,2)[0]['reason'],'MISSING_SAMPLE')
        with self.assertRaises(ValueError):plan(m,0,3,33)
    def test_actual_ticks_only(self):
        r=plan(manifest(),0,3);chosen=choose_ticks(Fraction(1,8),set(range(24)),r,{Fraction(0),Fraction(2)})
        self.assertEqual(list(chosen),[2,4,6,8,10,12,14]);self.assertTrue(all(x in range(24) for x in chosen))
    def test_reject_duplicate_seconds(self):
        m=manifest();m['frames'].insert(1,dict(m['frames'][0],pts='1/2'))
        with self.assertRaises(ValueError):plan(m,0,3)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class RefinementTests(unittest.TestCase):
    def test_exact_fractional_frames_and_no_overwrite(self):
        class Reader:
            def scan(self,image):return [row(1,True),row(2,True)]
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1504x696:r=4','-t','3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(p)],check=True,timeout=30)
            m=scan(p,0,3,reader=FixtureReader());m['frames'][0]['cards']=[row(1)];m['frames'][1]['cards']=[row(1,True)];m['frames'][2]['cards']=[row(1,True)]
            r=refine(p,m,0,3,Reader(),budget=1);self.assertEqual([x['pts'] for x in r['frames']],['1/4','1/2','3/4']);self.assertEqual(r['additional_complete_second_tables'],1);self.assertFalse(r['strategy_authorized']);self.assertFalse(r['coarse_frames_replaced']);self.assertIsNone(m['frames'][0]['cards'][0]['hero_cards'])
            for f in r['frames']:
                raw=subprocess.check_output(['ffmpeg','-v','error','-threads','1','-filter_threads','1','-ss',str(float(Fraction(f['pts']))),'-i',str(p),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-threads:v','1','pipe:1']);self.assertEqual(hashlib.sha256(raw).hexdigest(),f['rgb_sha256']);self.assertEqual([x['table_id'] for x in f['cards']],[1])
            m['source_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Source hash mismatch'):refine(p,m,0,3,Reader())

if __name__=='__main__':unittest.main()
