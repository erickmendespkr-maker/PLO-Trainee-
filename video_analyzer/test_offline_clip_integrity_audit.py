"""Synthetic FFmpeg tests for exported clip integrity and evidence gates."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from offline_clip_integrity_audit import audit_clip, digest

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clip = Path(self.tmp.name) / 'clip.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=10','-t','1','-c:v','libx264',
                        '-pix_fmt','yuv420p',str(self.clip)], check=True)
        self.report = {'clip_sha256':digest(self.clip),'analysis_status':'manually_selected_offline_clip',
                       'automatic_clip_selection_authorized':False,'video_evidence_verified':False,
                       'start_seconds':0,'end_seconds':1,'crop':{'width':160,'height':120},
                       'source_video_sha256':digest(self.clip)}
        self.save()
    def save(self):
        Path(str(self.clip)+'.json').write_text(json.dumps(self.report))
    def test_valid(self):
        self.assertTrue(audit_clip(self.clip)['verified'])
    def test_source_hash(self):
        self.assertTrue(audit_clip(self.clip,self.clip)['source_checked'])
    def test_tampered_hash(self):
        self.report['clip_sha256']='0'*64; self.save()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_promotion(self):
        self.report['video_evidence_verified']=True; self.save()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_bad_dimensions(self):
        self.report['crop']['width']=100; self.save()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_nonfinite_timestamp(self):
        self.report['end_seconds']=float('nan'); self.save()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_missing_sidecar(self):
        Path(str(self.clip)+'.json').unlink()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_duration_mismatch(self):
        self.report['end_seconds']=0.2; self.save()
        with self.assertRaises(ValueError): audit_clip(self.clip)
    def test_duplicate_json_key(self):
        Path(str(self.clip)+'.json').write_text('{"clip_sha256":"a","clip_sha256":"b"}')
        with self.assertRaises(ValueError): audit_clip(self.clip)
if __name__=='__main__': unittest.main()
