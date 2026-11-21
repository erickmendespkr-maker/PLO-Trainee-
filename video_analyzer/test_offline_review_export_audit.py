"""Synthetic regression tests for offline review export auditor."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_review_export_audit import audit_review_export

class ReviewExportAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.clip = root / 'hand.mp4'
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i',
                        'color=size=64x64:rate=10:duration=1','-c:v','mpeg4',
                        str(self.clip)], check=True)
        self.manifest = {'schema_version':1,
            'clip_sha256':hashlib.sha256(self.clip.read_bytes()).hexdigest(),
            'ev_is_conditional':True,'gto_solution':False,
            'human_review_of_export':False,'table_id':2,
            'source_duration_seconds':3,
            'requested_interval_seconds':[1,2],
            'evidence_gate':{'table_id':2,'start_pts':1,'end_pts':2,'can_label_error':False}}
        self.save()
    def save(self):
        self.clip.with_suffix('.json').write_text(json.dumps(self.manifest),encoding='utf-8')
    def test_valid(self):
        result = audit_review_export(self.clip)
        self.assertTrue(result['integrity_verified'])
        self.assertFalse(result['strategic_analysis_verified'])
    def test_tamper(self):
        self.clip.write_bytes(self.clip.read_bytes()+b'tampered')
        with self.assertRaisesRegex(ValueError,'checksum'):
            audit_review_export(self.clip)
    def test_missing_manifest(self):
        self.clip.with_suffix('.json').unlink()
        with self.assertRaises(ValueError):
            audit_review_export(self.clip)
    def test_wrong_table(self):
        self.manifest['table_id']=3
        self.save()
        with self.assertRaisesRegex(ValueError,'table mismatch'):
            audit_review_export(self.clip)
    def test_gto_claim(self):
        self.manifest['gto_solution']=True
        self.save()
        with self.assertRaisesRegex(ValueError,'disclaimers'):
            audit_review_export(self.clip)
    def test_invalid_interval(self):
        self.manifest['requested_interval_seconds']=[2,1]
        self.save()
        with self.assertRaises(ValueError):
            audit_review_export(self.clip)
    def test_source_required_hash(self):
        source=self.clip.parent/'source.mp4'
        source.write_bytes(b'source')
        with self.assertRaisesRegex(ValueError,'source checksum'):
            audit_review_export(self.clip,source=source)

if __name__=='__main__':
    unittest.main()
