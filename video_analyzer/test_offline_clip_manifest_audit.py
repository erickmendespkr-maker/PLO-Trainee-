import hashlib
import json
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_clip_manifest_audit import audit_clip_manifest, ManifestAuditError
except ImportError:
    from offline_clip_manifest_audit import audit_clip_manifest, ManifestAuditError

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.src, self.clip, self.side = d/'source.mp4', d/'clip.mp4', d/'clip.json'
        self.src.write_bytes(b'source-video')
        self.clip.write_bytes(b'clip-video')
        self.data = dict(schema_version=1, source_sha256=hashlib.sha256(self.src.read_bytes()).hexdigest(),
            clip_sha256=hashlib.sha256(self.clip.read_bytes()).hexdigest(), source_duration_seconds=20,
            requested_interval_seconds=[2, 5], table_id=2,
            evidence_gate={'table_id':2,'start_pts':2,'end_pts':5}, ev_is_conditional=True,
            gto_solution=False, human_review_of_export=False)
        self.save()
    def save(self):
        self.side.write_text(json.dumps(self.data))
    def check_rejected(self):
        with self.assertRaises(ManifestAuditError):
            audit_clip_manifest(self.src,self.clip,self.side)
    def test_valid(self):
        result = audit_clip_manifest(self.src,self.clip,self.side)
        self.assertEqual(result['status'], 'INTEGRITY_VERIFIED_ONLY')
        self.assertFalse(result['ev_verified'])
    def test_tampered_clip(self):
        self.clip.write_bytes(b'tampered')
        self.check_rejected()
    def test_tampered_source(self):
        self.src.write_bytes(b'tampered')
        self.check_rejected()
    def test_wrong_gate(self):
        self.data['evidence_gate']['table_id']=3; self.save(); self.check_rejected()
    def test_invalid_time(self):
        self.data['requested_interval_seconds']=[5,2]; self.save(); self.check_rejected()
    def test_out_of_bounds(self):
        self.data['source_duration_seconds']=3; self.save(); self.check_rejected()
    def test_false_gto(self):
        self.data['gto_solution']=True; self.save(); self.check_rejected()
    def test_false_human_review(self):
        self.data['human_review_of_export']=True; self.save(); self.check_rejected()
    def test_bad_table(self):
        self.data['table_id']=5; self.save(); self.check_rejected()
    def test_nonfinite(self):
        self.data['requested_interval_seconds']=[float('nan'),5]; self.save(); self.check_rejected()
    def test_missing_file(self):
        self.clip.unlink(); self.check_rejected()
    def test_unsupported_schema(self):
        self.data['schema_version']=2; self.save(); self.check_rejected()

if __name__ == '__main__':
    unittest.main()
