import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from ctypes.util import find_library
from plo5_integrated_video import SharedSeatReader, observe_shared, table_manifest, cfr_review, run, Cancelled
from plo5_integrated_desktop import command
from plo5_seat_evidence import SeatReader
from test_plo5_snapshot_replay import H,V,B,seed,snap,manifest
from plo5_snapshot_replay import replay
from plo5_selective_review import select
from plo5_terminal_bounds import review as terminal_review

BANK=Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json'

class IntegrationTests(unittest.TestCase):
    def test_targeted_seat_reader_matches_legacy(self):
        im=Image.new('RGB',(1504,696),'black');calls=[]
        def decoder(patch,platform,field):calls.append(field);return dict(candidate=None,raw='',confidence=None)
        with patch('plo5_seat_evidence.detect',return_value='pppoker'),patch('plo5_integrated_video.detect',return_value='pppoker'),patch('plo5_seat_evidence.dealer',return_value={'seat':None}),patch('plo5_integrated_video.dealer',return_value={'seat':None}):
            old=SeatReader(workers=1,decoder=decoder).scan(im);new=SharedSeatReader(workers=1,decoder=decoder)
            try:self.assertEqual(new.scan(im,[1,4]),[old[0],old[3]]);self.assertEqual(new.stats()['hits']+new.stats()['misses'],24)
            finally:new.close()
    def test_shared_decode_and_targeted_refined_frames(self):
        with tempfile.TemporaryDirectory() as t:
            v=Path(t)/'v.mp4';v.write_bytes(b'x');sha=hashlib.sha256(b'x').hexdigest();coarse=dict(variant=5,source_sha256=sha,frames=[dict(pts='0',rgb_sha256='a'*64)]);ref=dict(variant=5,source_sha256=sha,version='plo5-card-refinement-v1',frames=[dict(pts='1/4',rgb_sha256='b'*64,target_tables=[4])]);calls=[]
            class Reader:
                def scan(self,image):calls.append('scan');return [dict(table_id=t,platform=None) for t in range(1,5)]
            class Seats:
                def scan(self,image,tables):calls.append(tuple(sorted(tables)));return [dict(table_id=t,platform=None) for t in tables]
            def decode(source,points,expected,consume,timeout):
                for p in points:consume(p,Image.new('RGB',(1504,696),'black'))
            with patch('plo5_integrated_video.decode',side_effect=decode) as dec:
                r=observe_shared(v,coarse,ref,[1,4],Reader(),Reader(),Seats(),lambda im,t:dict(table_id=t,platform=None));self.assertEqual(dec.call_count,1);self.assertEqual(calls,['scan','scan',(1,4),'scan','scan',(4,)]);self.assertEqual(len(table_manifest(r,1)['frames']),1);self.assertEqual(len(table_manifest(r,4)['frames']),2)
            ref['frames'][0]['pts']='0'
            with self.assertRaisesRegex(ValueError,'Duplicate refinement PTS'):observe_shared(v,coarse,ref,[1,4],Reader(),Reader(),Seats(),lambda im,t:None)
    def test_native_cfr_and_terminal_contract(self):
        sd=seed();sd['initial']={'hero_bottom':4,'top':4};rows=[snap(0,3,3,2,'hero_bottom'),snap(1,4,2,2,'top'),snap(2,4,2,2,None),snap(3,4,2,2,'top',B[:3],True),snap(4,6,2,0,'hero_bottom',B[:3]),snap(5,8,0,0,None,B[:3])];r=replay(manifest(rows),sd,rows);data=dict(version='plo5-auto-reconstruction-candidates-v1',hands_reconstructed=False,strategy_authorized=False,hands=[dict(seed=sd,events=r['events'])],decision_records=r['decision_records']);cfg=dict(ranges={'SB':[dict(cards=H,weight=1)],'BB':[dict(cards=V,weight=1)]},rake_bps=0,rake_cap=0,rake_on_fold=False,iterations=1)
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as t,ExitStack() as stack:
            rank=None
            if os.environ.get('PLO5_RANK_WORKER_EXE'):
                from plo5_rank_worker import RankWorker
                rank=stack.enter_context(RankWorker(os.environ['PLO5_RANK_WORKER_EXE']))
            cache=Path(t)/'db.sqlite';a=cfr_review(data,{'h':cfg},['flop'],cache,native=os.environ.get('PLO5_MULTIWAY_EXE'),rank=rank);self.assertEqual(a[0]['estimate']['equity']['runouts'],741);self.assertFalse(a[0]['estimate']['strategy_verified']);self.assertEqual(a[0]['status'],'EXPERIMENTAL_MODEL_ONLY');b=cfr_review(data,{'h':cfg},['flop'],cache,native=os.environ.get('PLO5_MULTIWAY_EXE'),rank=rank);self.assertTrue(b[0]['estimate']['cache_hit'])
            d=next(d for d in data['decision_records'] if d['street']=='flop');cfg2=dict(hypotheses=[dict(id='test',provenance='synthetic',deals=[dict(holdings={'SB':H,'BB':V},weight=1)])],rake_bps=0,rake_cap=0,rake_on_fold=False);q=terminal_review(data,{'h':{d['decision_id']:cfg2}},['flop'],rank_worker=rank);self.assertEqual(q['estimates'][0]['status'],'CONDITIONAL_TERMINAL_BOUNDS');self.assertFalse(q['selection']['print_requests']);self.assertFalse(select(data['decision_records'])['errors'])
    @unittest.skipUnless(find_library('tesseract') and shutil.which('tesseract') and os.environ.get('OMP_THREAD_LIMIT')=='1','Native OCR requires matching local library')
    def test_native_seat_decoder_parity(self):
        from plo5_native_seats import NativeSeatOCR
        from plo5_seat_evidence import decode
        e=NativeSeatOCR()
        try:
            for platform in ('pppoker','suprema'):
                for field,text in [('stack','100,0 BB'),('action','Call')]:
                    im=Image.new('RGB',(67,15),'black' if field=='stack' or platform=='suprema' else 'white');ImageDraw.Draw(im).text((5,1),text,fill='white' if field=='stack' or platform=='suprema' else 'black')
                    self.assertEqual(e.decode(im,platform,field),decode(im,platform,field));self.assertEqual(e.decode(im,platform,field),decode(im,platform,field))
        finally:e.close()
    def test_gui_command(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);v=p/'a b.mp4';v.touch();bank=p/'bank.json';bank.touch();c=command(str(v),str(p/'out'),['river','flop'],[1,4],ppp=str(bank),start='10',seconds='8',cancel_file=p/'cancel');self.assertIn('plo5_integrated_video.py',Path(c[2]).name);self.assertEqual(c[c.index('--tables')+1:c.index('--workers')],['1','4']);self.assertIn('--cancel-file',c)
            with self.assertRaises(ValueError):command(str(v),str(p/'out'),['flop'],[1,1],ppp=str(bank))

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and BANK.exists(),'FFmpeg and bank required')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.p=Path(self.temp.name);self.v=self.p/'test.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(self.v)],check=True,timeout=30)
    def test_new_scan_and_resume(self):
        a=run(self.v,self.p/'one',chunk=2,ppp=BANK,tables=[1,4],workers=1,refine_budget=1);self.assertEqual(a['counts']['decoded_frames'],4);self.assertEqual(a['counts']['table_observations'],8);self.assertEqual(a['counts']['prints'],0);self.assertFalse(a['beta_ready']);self.assertFalse(a['drivehud_beta']);self.assertEqual(len(a['windows']),2)
        with patch('plo5_integrated_video.scan_session') as scan:
            b=run(self.v,self.p/'two',session=self.p/'one'/'recognition'/'session.json',chunk=2,ppp=BANK,tables=[1,4],workers=1,refine_budget=1);scan.assert_not_called();self.assertEqual(a['counts'],b['counts'])
    def test_cancel_atomic_output(self):
        cancel=self.p/'cancel';out=self.p/'cancelled'
        def progress(row):cancel.touch()
        with self.assertRaises(Cancelled):run(self.v,out,ppp=BANK,workers=1,chunk=2,progress=progress,cancel_file=cancel)
        self.assertFalse(out.exists());self.assertEqual(list(self.p.glob('.plo27-*')),[])
    def test_session_tamper(self):
        a=run(self.v,self.p/'one',chunk=2,ppp=BANK,workers=1,refine_budget=0);m=self.p/'one'/'recognition';(m/'window_00001.json').write_text('{}');out=self.p/'bad'
        with self.assertRaisesRegex(ValueError,'Window hash mismatch'):run(self.v,out,session=m/'session.json',ppp=BANK,workers=1,chunk=2)
        self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
