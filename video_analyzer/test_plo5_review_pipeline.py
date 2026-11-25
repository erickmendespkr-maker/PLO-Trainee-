import json
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from PIL import Image
from plo5_review_pipeline import run, sha
from test_plo5_window_review import window, B


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.ann=self.root/'ann.json';self.ann.write_text('{}');self.job={'database':'jobs.db','job_id':'a'*32,'annotations':str(self.ann)}
        self.windows={};self.audits=[];self.calls=[];self.binding={'job_id':'a'*32};self.out=self.root/'output'
        for n,start,boards in [(1,0,[[],[]]),(2,2,[B,B])]:
            t=window(n,start,boards)['timeline'];t['annotation_sha256']=sha(self.ann.read_bytes());folder=self.root/f'window_{n:02d}';folder.mkdir();paths={};t['frames']=[]
            for o in t['observations']:
                p=folder/o['file'];Image.new('RGB',(8,8),(30,40,50)).save(p);o['sha256']=sha(p.read_bytes());paths[o['file']]=p
            p=folder/'timeline.json';p.write_text(json.dumps(t));self.windows[p]=(t,sha(p.read_bytes()),self.binding,paths)
        mods={k:ModuleType(k) for k in ('plo5_financial_observations','plo5_recognition_cache','plo5_ingest_job','offline_video_ingest_probe','plo5_visual_report','plo5_dense_timeline')}
        def audit(job,p):self.audits.append(p);return self.windows[p]
        mods['plo5_financial_observations'].bound_window=audit;mods['plo5_financial_observations'].amount=lambda r:r
        calls=self.calls
        class Reader:
            def __init__(self,capacity):self.capacity=capacity
            def read(self,im,field):calls.append(field);return '100' if field=='stack' else '40'
            def stats(self):return {'calls':len(calls),'capacity':self.capacity}
        mods['plo5_recognition_cache'].ExactReader=Reader
        mods['plo5_ingest_job'].read_bound_evidence=lambda *args:self.binding
        mods['offline_video_ingest_probe'].sha256=lambda p:sha(Path(p).read_bytes())
        def visual(db,jid,draft,study,out,mode):
            out.mkdir();(out/'index.html').write_text(mode);return {}
        mods['plo5_visual_report'].run=visual
        self.mods=mods;self.patch=patch.dict('sys.modules',mods);self.patch.start();self.addCleanup(self.patch.stop)
    def execute(self,**kwargs):return run(self.job,list(self.windows),self.out,**kwargs)
    def test_package(self):
        r=self.execute();self.assertEqual(r['windows'],2);self.assertEqual(r['observations'],4);self.assertEqual(r['candidate_segments'],1);self.assertEqual(len(self.audits),2);self.assertEqual(len(self.calls),8)
        self.assertFalse(r['hands_reconstructed']);self.assertFalse(r['financial_result_verified']);self.assertEqual(r['mp4_rendered'],0)
        for p in r['prints']:self.assertEqual(sha((self.out/p['file']).read_bytes()),p['sha256'])
        self.assertEqual(len(json.loads((self.out/'money.json').read_text())),2)
        self.assertIn('não comprova perda',(self.out/'index.html').read_text())
    def test_study_separate(self):
        d=self.root/'draft';s=self.root/'study';d.write_text('{}');s.write_text('{}');r=self.execute(study={'drafts':d,'study_input':s},mode='deep')
        self.assertTrue(r['study_present']);self.assertFalse(r['dense_strategy_link_verified']);self.assertEqual((self.out/'study/index.html').read_text(),'deep');self.assertIn('sem associação automática',(self.out/'index.html').read_text())
    def test_changed_crop(self):
        p=next(iter(self.windows.values()))[3]['table_01_001.png'];p.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'Crop changed'):self.execute()
        self.assertFalse(self.out.exists())
    def test_recheck(self):
        self.mods['plo5_ingest_job'].read_bound_evidence=lambda *args:None
        with self.assertRaisesRegex(ValueError,'Inputs changed'):self.execute()
        self.assertFalse(self.out.exists())
    def test_existing_output(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError,'New output'):self.execute()
        self.assertEqual(self.audits,[])
    def test_invalid_settings(self):
        with self.assertRaisesRegex(ValueError,'Invalid settings'):self.execute(workers=4)
        self.assertFalse(self.out.exists())
    def test_extract_wrong_job(self):
        self.mods['plo5_dense_timeline'].run=lambda *args,**kw:None
        with self.assertRaisesRegex(ValueError,'Wrong extraction job'):run(self.job,[{'job_id':'wrong'}],self.out,extract=True)
        self.assertFalse(self.out.exists())

if __name__=='__main__':unittest.main()
