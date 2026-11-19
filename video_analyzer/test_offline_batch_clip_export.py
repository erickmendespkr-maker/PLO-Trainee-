"""Integration tests using synthetic MP4 and real FFmpeg/FFprobe."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from offline_batch_clip_export import export_reviewed_clips,video_info

class BatchClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.video=self.base/'sample.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x240:rate=10','-t','3','-c:v','libx264',str(self.video)],check=True)
        self.hash=hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.plan=self.base/'plan.json'
        self.obj={'schema_version':1,'source_video_sha256':self.hash,'analysis_verified':False,
                  'clip_plans':[{'hand_id':'h1','table_id':1,'clip_start_seconds':0.2,
                                 'clip_end_seconds':1.5,'crop_xywh':[0,0,160,120],
                                 'boundaries_verified':True,'strategy_verified':False,
                                 'analysis_label':'INSUFFICIENT_DATA'}]}
        self.write()
    def write(self): self.plan.write_text(json.dumps(self.obj),encoding='utf-8')
    def test_export_mp4_and_manifest(self):
        result=export_reviewed_clips(self.video,self.plan,self.base/'out')
        clip=self.base/'out'/result['clips'][0]['clip']
        self.assertTrue(clip.exists());self.assertEqual(video_info(clip)[:2],(160,120))
        self.assertFalse(result['analysis_verified']);self.assertEqual(result['clips'][0]['analysis_label'],'INSUFFICIENT_DATA')
    def test_wrong_hash(self):
        self.obj['source_video_sha256']='0'*64;self.write()
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
    def test_unreviewed(self):
        self.obj['clip_plans'][0]['boundaries_verified']=False;self.write()
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
    def test_out_of_bounds_crop(self):
        self.obj['clip_plans'][0]['crop_xywh']=[200,0,160,120];self.write()
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
    def test_out_of_bounds_time(self):
        self.obj['clip_plans'][0]['clip_end_seconds']=4;self.write()
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
    def test_unsafe_id(self):
        self.obj['clip_plans'][0]['hand_id']='../bad';self.write()
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
    def test_existing_manifest_does_not_export_clips(self):
        out=self.base/'out';out.mkdir();(out/'clip_manifest.json').write_text('{}')
        with self.assertRaises(FileExistsError): export_reviewed_clips(self.video,self.plan,out)
        self.assertEqual(list(out.glob('*.mp4')),[])
    def test_later_existing_clip_does_not_export_first(self):
        second=dict(self.obj['clip_plans'][0]);second['hand_id']='h2'
        self.obj['clip_plans'].append(second);self.write()
        out=self.base/'out';out.mkdir();(out/'table1_h2.mp4').write_bytes(b'keep')
        with self.assertRaises(FileExistsError): export_reviewed_clips(self.video,self.plan,out)
        self.assertFalse((out/'table1_h1.mp4').exists())
        self.assertEqual((out/'table1_h2.mp4').read_bytes(),b'keep')
    def test_duplicate_filename_rejected_before_export(self):
        second=dict(self.obj['clip_plans'][0]);second['table_id']=2
        self.obj['clip_plans'].append(second);self.write()
        # Duplicate hand IDs are already rejected by the handoff validator.
        with self.assertRaises(ValueError): export_reviewed_clips(self.video,self.plan,self.base/'out')
        self.assertFalse((self.base/'out').exists())
    def test_no_overwrite(self):
        export_reviewed_clips(self.video,self.plan,self.base/'out')
        with self.assertRaises(FileExistsError): export_reviewed_clips(self.video,self.plan,self.base/'out')

if __name__=='__main__': unittest.main()
