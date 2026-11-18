"""End-to-end synthetic export followed by independent provenance verification."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from offline_reviewed_clip_executor import export_reviewed_clip
from offline_clip_provenance_audit import audit_export


def reviewed_plan(source):
    plan = {'status': 'READY_FOR_OFFLINE_EXPORT', 'hand_id': 'synthetic-hand',
            'table_id': 2, 'start_pts': .2, 'end_pts': 1.2,
            'video_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'explanation': 'Hypothetical ranges; no GTO claim',
            'conditional_model_only': True, 'not_gto': True,
            'requires_source_hash_check': True}
    plan['manifest_sha256'] = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return plan


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class ExportAuditIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'session.mp4'
        self.clip = self.root / 'review.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10', '-t', '2', '-c:v', 'mpeg4',
                        str(self.source)], check=True, capture_output=True)
        self.plan = reviewed_plan(self.source)

    def test_export_then_audit(self):
        meta = export_reviewed_clip(self.source, self.plan, self.clip)
        report = audit_export(self.clip, source=self.source)
        self.assertEqual(report['status'], 'MEDIA_PROVENANCE_VERIFIED')
        self.assertEqual(report['hand_id'], 'synthetic-hand')
        self.assertEqual(meta['reviewed_explanation'], self.plan['explanation'])
        self.assertFalse(report['strategy_validated'])
        self.assertFalse(report['human_review_independently_verified'])

    def test_modified_explanation_rejected(self):
        export_reviewed_clip(self.source, self.plan, self.clip)
        sidecar = Path(str(self.clip) + '.json')
        data = json.loads(sidecar.read_text())
        data['reviewed_explanation'] = ''
        sidecar.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'reviewed explanation'):
            audit_export(self.clip, source=self.source)

    def test_modified_source_rejected(self):
        export_reviewed_clip(self.source, self.plan, self.clip)
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'source SHA-256'):
            audit_export(self.clip, source=self.source)


if __name__ == '__main__':
    unittest.main()
