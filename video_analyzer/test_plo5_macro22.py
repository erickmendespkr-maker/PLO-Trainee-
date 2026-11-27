import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from ctypes.util import find_library
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont
from plo5_fast_money import FastMoneyReader,NativeOCR
from plo5_bounded_session import windows,run
from plo5_rank_lru import CachedRankWorker
from plo5_visual_codes import MixedReader,pixels
from plo5_mixed_money import read,REGIONS


class OptimizationTests(unittest.TestCase):
    def test_window_partition(self):
        self.assertEqual(list(windows(10,241,120)),[(10,81),(91,80),(171,80)])
        self.assertEqual(list(windows(0,121,120)),[(0,61),(61,60)])
        for args in ((0,1,120),(0,5,2),(0,10,121)):
            with self.assertRaises(ValueError):list(windows(*args))
    def test_cli_cache_and_close(self):
        im=Image.new('RGB',(1504,696),'black')
        with FastMoneyReader(8,1) as reader:
            self.assertEqual(reader.scan(im),MixedReader(8,1).scan(im));reader.scan(im)
            self.assertEqual(reader.calls,0);self.assertEqual(reader.layout.stats()['hits'],7)
        with self.assertRaises(ValueError):reader.scan(im)
    @unittest.skipUnless(find_library('tesseract') and shutil.which('tesseract') and os.environ.get('OMP_THREAD_LIMIT')=='1','Native OCR test requires lib and OMP_THREAD_LIMIT=1')
    def test_native_roi_parity(self):
        im=Image.new('RGB',(1504,696),'white');draw=ImageDraw.Draw(im)
        for field,txt in [('stack','100,0 BB'),('pot','Pot: 2,5 BB')]:
            x,y,z,w=REGIONS['pppoker'][field];draw.text((x,y),txt,fill='black',font=ImageFont.load_default())
        engine=NativeOCR()
        try:
            for field in ('stack','pot'):
                rect=REGIONS['pppoker'][field];patch=pixels(im,rect,'L');old=read(im,1,'pppoker',field)
                self.assertEqual(engine.read(patch,'pppoker',field),old);self.assertEqual(engine.read(patch,'pppoker',field),old)
        finally:engine.close()
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg absent')
    def test_bounded_session(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);v=p/'v.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','5','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],check=True,timeout=30)
            out=p/'report';r=run(v,out,0,5,chunk=3,workers=1);self.assertEqual(r['frames'],5);self.assertEqual(len(r['windows']),2);self.assertEqual(r['missing_sample_seconds'],0);self.assertFalse(r['strategy_authorized']);self.assertFalse(r['drivehud_beta'])
            ids=[]
            for w in r['windows']:
                data=(out/w['file']).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),w['sha256']);m=json.loads(data);ids.extend(f['file'] for f in m['frames'])
            self.assertEqual(len(set(ids)),5);self.assertEqual(r['ocr_calls'],0);self.assertEqual(list(out.glob('*.png')),[])
            with self.assertRaises(ValueError):run(v,out,0,5,chunk=3)
    def test_rank_cache_eviction_and_validation(self):
        class Worker:
            def __init__(self):self.calls=[]
            def lookup(self,street,states):
                self.calls.append(len(states));return [dict(index=i,rank=10,source='NATIVE_COMPUTED') for i,_ in enumerate(states)]
        w=Worker();c=CachedRankWorker(w,1);h=['As','Ks','Qh','Jd','Tc'];b=['2c','3d','4h'];d=['2c','3d','5h']
        x=c.lookup(3,[(h,b),(h,b)]);self.assertEqual(w.calls,[1]);x[0]['rank']=99;self.assertEqual(c.lookup(3,[(h,b)])[0]['rank'],10)
        c.lookup(3,[(h,d)]);c.lookup(3,[(h,b)]);self.assertEqual(w.calls,[1,1,1]);self.assertEqual(c.stats()['entries'],1)
        with self.assertRaises(ValueError):c.lookup(3,[(h,['As','3d','4h'])])
    @unittest.skipUnless(os.environ.get('PLO5_RANK_WORKER_EXE'),'Native rank worker absent')
    def test_native_rank_cache_parity(self):
        from plo5_rank_worker import RankWorker
        h=['As','Ks','Qh','Jd','Tc'];b=['2c','3d','4h','5s','6s'];states=[(h,b),(h,b[::-1]),(h,b)]
        with RankWorker(os.environ['PLO5_RANK_WORKER_EXE']) as w:
            ref=w.lookup(5,states);c=CachedRankWorker(w,8);self.assertEqual(c.lookup(5,states),ref);self.assertEqual(c.lookup(5,states),ref);self.assertEqual(c.stats()['hits'],3)

if __name__=='__main__':unittest.main()
