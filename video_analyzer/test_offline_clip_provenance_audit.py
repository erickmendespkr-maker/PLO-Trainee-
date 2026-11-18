"""Synthetic FFmpeg regression tests for read-only MP4 provenance audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from offline_clip_provenance_audit import audit_export


class ProvenanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=160x120:r=10', '-t', '1', '-c:v', 'mpeg4', str(self.clip)],
                       check=True, capture_output=True)
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(self.clip.read_bytes())
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        self.meta = {'schema_version': 1, 'source_sha256': sha(self.source),
                     'plan_sha256': 'a' * 64, 'clip_sha256': sha(self.clip),
                     'table_id': 1, 'hand_id': 'synthetic', 'start_pts': 0.0,
                     'end_pts': 1.0, 'clip_duration_seconds': 1.0,
                     'reviewed_explanation': 'Synthetic review only',
                     'conditional_model_only': True, 'not_gto': True, 'audio_included': False}
        self.save()

    def save(self):
        Path(str(self.clip) + '.json').write_text(json.dumps(self.meta), encoding='utf8')

    def test_valid_media(self):
        report = audit_export(self.clip, source=self.source)
        self.assertEqual(report['status'], 'MEDIA_PROVENANCE_VERIFIED')
        self.assertFalse(report['strategy_validated'])
        self.assertTrue(report['source_checked'])

    def test_optional_source_not_claimed(self):
        self.assertFalse(audit_export(self.clip)['source_checked'])

    def test_tampered_mp4(self):
        with self.clip.open('ab') as f: f.write(b'bad')
        with self.assertRaisesRegex(ValueError, 'MP4 SHA'): audit_export(self.clip)

    def test_wrong_source(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'source SHA'): audit_export(self.clip, source=self.source)

    def test_wrong_duration(self):
        self.meta['end_pts'] = 2.0
        self.save()
        with self.assertRaisesRegex(ValueError, 'duration mismatch'): audit_export(self.clip)

    def test_invalid_table(self):
        self.meta['table_id'] = 5
        self.save()
        with self.assertRaisesRegex(ValueError, 'invalid table'): audit_export(self.clip)

    def test_missing_review(self):
        self.meta['reviewed_explanation'] = ''
        self.save()
        with self.assertRaisesRegex(ValueError, 'reviewed explanation'): audit_export(self.clip)

    def test_false_gto_guard(self):
        self.meta['not_gto'] = False
        self.save()
        with self.assertRaisesRegex(ValueError, 'safeguards'): audit_export(self.clip)

    def test_corrupt_json(self):
        Path(str(self.clip) + '.json').write_text('{broken', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'invalid JSON'): audit_export(self.clip)


if __name__ == '__main__':
    unittest.main()
