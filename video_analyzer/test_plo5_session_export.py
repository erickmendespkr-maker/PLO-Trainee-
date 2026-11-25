import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_plo5_decision_analysis as bridge
from local_ingest import ingest_local
from plo5_ingest_job import run_job, read_bound_evidence
from offline_ingest_pts_audit import read_manifest, decoded_pts
from offline_jobs import OfflineJobStore
from offline_video_ingest_probe import sha256
from plo5_session_export import plan, run, verify, render


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        v=cls.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=256x128:rate=10:duration=3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],check=True)
        cls.db=cls.root/'jobs.db';job=ingest_local(v,cls.root/'uploads',cls.db);cls.jid=job['job_id']
        p=cls.root/'regions.json';p.write_text(json.dumps({'tables':[{'table_id':i,'x':(i-1)*128,'y':0,'width':128,'height':128} for i in (1,2)]}))
        res=run_job(cls.db,cls.jid,p,cls.root/'evidence',pixel_checks=2)
        cls.binding=read_bound_evidence(cls.db,cls.jid);cls.manifest=read_manifest(Path(res['result_path']).parent/'evidence/ingest/manifest.json');cls.pts=decoded_pts(v)
        _,_,drafts,review,_=bridge.fixture()
        drafts.update(job_id=cls.jid,source_sha256=cls.binding['source_sha256'],manifest_sha256=cls.binding['reports']['evidence/ingest/manifest.json'])
        orig=copy.deepcopy(drafts['drafts'][0]);drafts['drafts']=[];reports=[];expected=[]
        for tid in (1,2):
            d=copy.deepcopy(orig);d.update(draft_id=f'd{tid}',table_id=tid)
            fs=d['frames'];fs.append(copy.deepcopy(fs[-1]))
            samples=sorted((s for s in cls.manifest['samples'] if s['table_id']==tid),key=lambda s:s['actual_frame_timestamp_seconds'])
            for f,s in zip(fs,samples):f.update(file=s['file'],pts=s['actual_frame_timestamp_seconds'],crop_sha256=s['sha256'])
            drafts['drafts'].append(d)
        cls.dp=cls.root/'drafts.json';cls.dp.write_text(json.dumps(drafts));cls.dh=sha256(cls.dp);cls.drafts=drafts
        t=bridge.BridgeTests();t.setUp()
        try:
            for d in drafts['drafts']:
                fs=d['frames'];r=copy.deepcopy(review);r.update(job_id=cls.jid,draft_sha256=cls.dh,draft_id=d['draft_id'],context_file=fs[0]['file'],action_file=fs[1]['file'])
                reports.append(bridge.d.analyze_review(cls.binding,cls.manifest,drafts,r,cls.dh,t.edb,t.sdb))
                expected.append({'draft_id':d['draft_id'],'action_file':fs[1]['file']})
                expected.append({'draft_id':d['draft_id'],'action_file':fs[2]['file']})
        finally:t.doCleanups()
        cls.request={'bundle':{'variant':5,'job_id':cls.jid,'source_sha256':cls.binding['source_sha256'],'manifest_sha256':drafts['manifest_sha256'],'draft_sha256':cls.dh,'draft_ids':['d1','d2'],'expected_decisions':expected,'reports':reports,'financial_report':None},'clip_reviews':[{'draft_id':'d1','start_pts':cls.pts[0],'end_pts':cls.pts[-1],'reviewer':'fixture','complete_by_review':True}]}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def request_copy(self):return copy.deepcopy(self.request)
    def planning(self,r=None,d=None):return plan(self.binding,self.manifest,d or self.drafts,self.dh,r or self.request,self.pts)
    def export(self,r,name):
        p=self.root/(name+'.json');p.write_text(json.dumps(r));out=self.root/name
        result=run(self.db,self.jid,self.dp,p,out);self.assertEqual(result,verify(out));return out

    def test_real_mp4_package_and_links(self):
        out=self.export(self.request_copy(),'package');s=json.loads((out/'session.json').read_text())
        self.assertEqual(s['overall']['declared_decisions'],4);self.assertEqual(s['overall']['fully_comparable_decisions'],2)
        self.assertEqual(s['unreviewed_clip_draft_ids'],['d2']);self.assertEqual(len(s['clips']),1);c=s['clips'][0]
        self.assertEqual((c['frames'],c['width'],c['height']),(30,128,128));self.assertTrue(c['decoded_yuv420p_pixels_match']);self.assertTrue(c['relative_pts_audited']);self.assertFalse(c['complete_hand_verified'])
        self.assertEqual([x['clip'] for x in s['exported_decisions']],['hand_0001.mp4',None]);self.assertEqual(c['decision_files'],['decision_00001.json'])
        self.assertIn('sem corte',(out/'session.txt').read_text());self.assertFalse(s['full_session_coverage_verified'])
        (out/'decision_00001.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):verify(out)

    def test_no_automatic_clips(self):
        r=self.request_copy();r['clip_reviews']=[];out=self.export(r,'reports_only');s=json.loads((out/'session.json').read_text());self.assertEqual(s['clips'],[]);self.assertEqual(s['unreviewed_clip_draft_ids'],['d1','d2']);self.assertEqual(len(list(out.glob('*.mp4'))),0)

    def test_two_tables_overlapping_time(self):
        r=self.request_copy();r['clip_reviews'].append(dict(r['clip_reviews'][0],draft_id='d2'));out=self.export(r,'two_tables');s=json.loads((out/'session.json').read_text());self.assertEqual(len(s['clips']),2);self.assertNotEqual(s['clips'][0]['sha256'],s['clips'][1]['sha256']);self.assertEqual([c['table_id'] for c in s['clips']],[1,2])

    def test_invalid_bounds_and_review(self):
        for key,value in [('complete_by_review',False),('reviewer',''),('start_pts',.001),('end_pts',.2),('draft_id','unknown')]:
            r=self.request_copy();r['clip_reviews'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.planning(r)
        r=self.request_copy();r['clip_reviews']*=2
        with self.assertRaises(ValueError):self.planning(r)

    def test_mixed_identity_and_report_evidence(self):
        for key in ('job_id','source_sha256','manifest_sha256','draft_sha256'):
            r=self.request_copy();r['bundle'][key]='f'*len(r['bundle'][key])
            with self.subTest(key=key),self.assertRaises(ValueError):self.planning(r)
        r=self.request_copy();r['bundle']['reports'][0]['context_pts']+=.01
        with self.assertRaisesRegex(ValueError,'Unbound decision'):self.planning(r)
        r=self.request_copy();r['bundle']['expected_decisions'][-1]['action_file']='unknown.jpg'
        with self.assertRaisesRegex(ValueError,'Unbound expected'):self.planning(r)

    def test_draft_coverage_and_unassigned(self):
        d=copy.deepcopy(self.drafts);f=d['drafts'][0]['frames'].pop();d['unassigned']=[dict(f,table_id=1)]
        r=self.request_copy();r['bundle']['expected_decisions'].pop(1)
        with self.assertRaisesRegex(ValueError,'crosses unrelated'):self.planning(r,d)
        d=copy.deepcopy(self.drafts);d['drafts'][0]['frames'][0]['crop_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'frame mismatch'):self.planning(d=d)

    def test_failure_cleanup_and_no_overwrite(self):
        r=self.request_copy();p=self.root/'failure.json';p.write_text(json.dumps(r));out=self.root/'failure'
        with patch('plo5_session_export.render',side_effect=ValueError('failure')):
            with self.assertRaisesRegex(ValueError,'failure'):run(self.db,self.jid,self.dp,p,out)
        self.assertFalse(out.exists());out.mkdir();(out/'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError,'New output'):run(self.db,self.jid,self.dp,p,out)
        self.assertEqual((out/'keep').read_text(),'keep')

    def test_vfr_nonzero_trim(self):
        v=self.root/'vfr.mp4';out=self.root/'trim.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=128x128:r=10:d=2','-vf',"select='not(eq(mod(n,3),1))'",'-fps_mode','vfr','-c:v','libx264','-threads','1',str(v)],check=True)
        pts=decoded_pts(v);p={'region':{'width':64,'height':64,'x':32,'y':32},'start_frame':2,'end_frame_inclusive':8};m=render(v,out,p,pts)
        self.assertEqual(m['frames'],7);self.assertTrue(m['decoded_yuv420p_pixels_match']);self.assertEqual(len(decoded_pts(out)),7)


if __name__=='__main__':unittest.main()
