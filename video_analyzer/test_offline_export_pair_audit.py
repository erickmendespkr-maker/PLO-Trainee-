"""FFmpeg synthetic regression tests for schema-v1 exported MP4 sidecars."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from offline_export_pair_audit import audit_export_pair, sha256

class ExportPairTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clip = Path(tmp.name) / 'clip.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=10','-t','1','-c:v','mpeg4',str(self.clip)],
                       check=True,timeout=30)
        self.data = dict(schema_version=1, source_sha256=sha256(self.clip),
                         clip_sha256=sha256(self.clip), strategic_verdict_allowed=False,
                         review_status='insufficient_data', annotation='INSUFFICIENT_DATA',
                         start_seconds=0, end_seconds=1, actual_clip_duration_seconds=1)
        self.save()
    def save(self):
        Path(str(self.clip)+'.json').write_text(json.dumps(self.data),encoding='utf-8')
    def reject(self):
        self.save()
        with self.assertRaises(ValueError): audit_export_pair(self.clip)
    def test_valid(self):
        self.assertTrue(audit_export_pair(self.clip)['artifact_integrity_verified'])
    def test_source(self):
        self.assertTrue(audit_export_pair(self.clip,self.clip)['source_checked'])
    def test_wrong_source(self):
        with self.assertRaises(ValueError): audit_export_pair(self.clip,Path(str(self.clip)+'.json'))
    def test_tamper(self):
        self.data['clip_sha256']='0'*64; self.reject()
    def test_promotion(self):
        self.data['strategic_verdict_allowed']=True; self.reject()
    def test_label(self):
        self.data['annotation']='GTO SOLVED'; self.reject()
    def test_nan(self):
        self.data['actual_clip_duration_seconds']=float('nan'); self.reject()
    def test_duration(self):
        self.data['actual_clip_duration_seconds']=0.5; self.reject()
    def test_missing(self):
        Path(str(self.clip)+'.json').unlink()
        with self.assertRaises(ValueError): audit_export_pair(self.clip)
    def test_duplicate(self):
        Path(str(self.clip)+'.json').write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): audit_export_pair(self.clip)
    def test_confirmed_still_conditional(self):
        self.data['review_status']='confirmed'
        self.data['annotation']='CONDITIONAL MODEL ONLY'
        self.save()
        self.assertFalse(audit_export_pair(self.clip)['strategic_analysis_verified'])

if __name__=='__main__': unittest.main()
