import copy
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from plo5_error_prints import bind,capture,anchor_candidates,frame_index,groups
from plo5_video_stream import scan
from test_plo5_selective_review import row
from fractions import Fraction


class FixtureReader:
    def __init__(self):self.cache=self.layout=self
    def stats(self):return {}
    def scan(self,image):
        return [dict(table_id=t,platform='pppoker' if t<=2 else None,field=f,value_bb=None,layout_candidate_active=t<=2) for t in range(1,5) for f in ('stack','pot')]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg absent')
class PrintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.video=cls.root/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1504x696:r=4','-t','3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(cls.video)],check=True,timeout=30)
        cls.manifest=scan(cls.video,0,3,reader=FixtureReader())
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def decision(self,ident='a',street='flop',pts='1',table=1,**kwargs):
        d=row(street,ident,**kwargs);d['evidence']=bind(self.manifest,d,pts,table,'before');return d
    def test_exact_crop_dedup_and_filter(self):
        d=[self.decision(),self.decision('b'),self.decision('c',table=2),self.decision('d',street='turn',pts='2'),self.decision('e',lo=2,hi=2),self.decision('f',hi=1)]
        out=self.root/'capture';r=capture(self.video,self.manifest,d,out,['flop'])
        self.assertEqual((r['selected_errors'],r['unique_frames'],r['unique_crops'],r['adequate_count'],r['unresolved_count']),(3,1,2,1,1))
        a,b,c=r['decision_prints'];self.assertEqual(a['file'],b['file']);self.assertNotEqual(a['file'],c['file']);self.assertFalse(r['semantic_binding_verified'])
        raw=subprocess.check_output(['ffmpeg','-v','error','-threads','1','-filter_threads','1','-ss','1','-i',str(self.video),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-threads:v','1','pipe:1'])
        im=Image.frombytes('RGB',(1504,696),raw)
        for e in (a,c):
            p=out/e['file'];self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),e['png_sha256'])
            with Image.open(p) as crop:self.assertEqual(crop.tobytes(),im.crop(e['crop']).tobytes())
    def test_no_errors_no_decode(self):
        with patch('plo5_error_prints.decode') as decoder:
            r=capture(self.video,self.manifest,[self.decision(lo=2,hi=2)],self.root/'empty');decoder.assert_not_called();self.assertEqual(r['unique_crops'],0)
    def test_reject_tampered_reference_and_rgb(self):
        a=self.decision();a['evidence']['rgb_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Reference does not match'):capture(self.video,self.manifest,[a],self.root/'bad')
        m=copy.deepcopy(self.manifest);m['frames'][1]['rgb_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'RGB hash mismatch'):capture(self.video,m,[a],self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
    def test_binding_guards(self):
        a=self.decision()
        for pts,t in (('1/2',1),('1',3)):
            with self.assertRaises(ValueError):bind(self.manifest,a,pts,t,'after')
        m=copy.deepcopy(self.manifest);m['frames'][1]['cards']=[dict(table_id=1,board_cards=['2c','3c','4c','5c'])]
        with self.assertRaisesRegex(ValueError,'street mismatch'):bind(m,a,'1',1,'before')
        m['frames'][1]['pts']='0'
        with self.assertRaises(ValueError):frame_index(m)
    def test_anchor_labels_not_actions(self):
        a=dict(status='CONSISTENT_DISPLAY_DELTAS',before_pts='0',after_pts='1',table_id=1,label_changes={'hero_bottom':[None,'call']})
        r=anchor_candidates(self.manifest,[a,dict(a,status='GAP'),dict(a,label_changes={'hero_bottom':['call','call']})]);self.assertEqual(len(r),1);self.assertFalse(r[0]['action_verified'])
        self.assertEqual([len(x) for x in groups(map(Fraction,[0,1,15,16,50]))],[3,1,1])
    def test_fractional_timestamp(self):
        raw=subprocess.check_output(['ffmpeg','-v','error','-threads','1','-filter_threads','1','-ss','0.25','-i',str(self.video),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-threads:v','1','pipe:1'])
        m=copy.deepcopy(self.manifest);f=copy.deepcopy(m['frames'][0]);f.update(pts='1/4',rgb_sha256=hashlib.sha256(raw).hexdigest());m['frames'].insert(1,f)
        d=row();d['evidence']=bind(m,d,'1/4',1,'before');r=capture(self.video,m,[d],self.root/'fractional')
        e=r['decision_prints'][0];self.assertEqual(e['pts'],'1/4');self.assertEqual(e['error']['severity'],'marginal')
        with Image.open(self.root/'fractional'/e['file']) as im:self.assertEqual(im.tobytes(),Image.frombytes('RGB',(1504,696),raw).crop(e['crop']).tobytes())
    def test_missing_evidence_preserves_error(self):
        d=self.decision();d['evidence']=None
        r=capture(self.video,self.manifest,[d],self.root/'missing')
        self.assertEqual(r['missing_references'],1);self.assertEqual(r['errors'][0]['decision_id'],'a')
        self.assertEqual(r['errors'][0]['evidence_status'],'MISSING_REFERENCE');self.assertEqual(r['unique_crops'],0)
    def test_source_mismatch(self):
        m=dict(self.manifest,source_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'Source hash mismatch'):capture(self.video,m,[],self.root/'badsource')

if __name__=='__main__':unittest.main()
