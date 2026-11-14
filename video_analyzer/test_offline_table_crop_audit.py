import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_table_crop_audit import audit_table_crops

class CropAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mkv'
        self.out = self.root / 'crops'
        self.out.mkdir()
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=128x96:rate=10:duration=3',
                        '-c:v','ffv1',str(self.source)],check=True)
        subprocess.run(['ffmpeg','-v','error','-ss','0.5','-i',str(self.source),'-t','2',
                        '-vf','crop=64:48:0:0','-c:v','ffv1',str(self.out/'table_1.mkv')],check=True)
        self.manifest = {'status':'UNREVIEWED_TABLE_CROPS','poker_analysis_verified':False,
                         'source_dimensions':[128,96], 'tables':[{'table_id':1,'file':'table_1.mkv',
                         'region':{'table_id':1,'x':0,'y':0,'width':64,'height':48},
                         'source_start_seconds':0.5,'requested_duration_seconds':2,
                         'verified_by_human':False,'hand_reconstructed':False}]}
        self.save()
    def save(self):
        (self.out/'manifest.json').write_text(json.dumps(self.manifest))
    def test_valid_crop(self):
        result=audit_table_crops(self.source,self.out)
        self.assertEqual(result['status'],'TECHNICAL_CROPS_AUDITED_ONLY')
        self.assertEqual(result['tables'][0]['decoded_frames'],20)
        self.assertFalse(result['hands_verified'])
    def test_wrong_dimensions(self):
        self.manifest['tables'][0]['region']['width']=63;self.save()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)
    def test_wrong_file(self):
        self.manifest['tables'][0]['file']='../../outside';self.save()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)
    def test_claims(self):
        self.manifest['tables'][0]['verified_by_human']=True;self.save()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)
    def test_missing_crop(self):
        (self.out/'table_1.mkv').unlink()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)
    def test_bad_interval(self):
        self.manifest['tables'][0]['requested_duration_seconds']=8;self.save()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)
    def test_bad_tolerance(self):
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out,duration_tolerance=float('nan'))
    def test_source_changed(self):
        self.manifest['source_dimensions']=[200,200];self.save()
        with self.assertRaises(ValueError): audit_table_crops(self.source,self.out)

if __name__ == '__main__': unittest.main()
