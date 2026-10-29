"""Tamper-detection and FFprobe tests for a synthetic offline clip bundle."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from offline_clip_artifact_audit import audit, digest
from offline_reviewed_clip_pipeline import run


def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n', 'utf-8')


class ArtifactAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=10',
                        '-t', '4', '-c:v', 'libx264', '-y', str(cls.video)],
                       check=True, timeout=60)
        drafts = cls.root / 'drafts.json'
        review = cls.root / 'review.json'
        crop = cls.root / 'crop.json'
        write(drafts, {'schema_version': 1,
                       'analysis_status': 'offline_reviewed_hand_drafts_only',
                       'source_reviewed_report_sha256': 'a' * 64,
                       'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
                       'hands': [{'hand_id': 'H1', 'table_id': 2, 'variant': 'PLO5',
                                  'start_seconds': 1, 'end_seconds': 3,
                                  'boundary_origin': 'manual_unverified',
                                  'status': 'draft_requires_human_reconstruction',
                                  'ready_for_equity_or_ev': False}]})
        write(review, {'schema_version': 1,
                       'analysis_status': 'offline_boundary_review_import_only',
                       'source_hand_drafts_sha256': digest(drafts),
                       'source_reviewed_report_sha256': 'a' * 64,
                       'ready_for_equity_or_ev': False,
                       'reviewed_boundaries_are_poker_verified': False,
                       'annotations': [{'hand_id': 'H1', 'table_id': 2,
                                        'review_status': 'confirmed', 'changed': False,
                                        'review_note': '', 'source_start_seconds': 1,
                                        'source_end_seconds': 3,
                                        'revised_start_seconds': 1,
                                        'revised_end_seconds': 3}]})
        write(crop, {'x': 160, 'y': 0, 'width': 160, 'height': 120})
        cls.original = cls.root / 'original'
        run(cls.video, drafts, review, 'H1', crop, cls.original)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        self.bundle = Path(self.tmp2.name) / 'bundle'
        shutil.copytree(self.original, self.bundle)

    def mutate(self, filename, change):
        path = self.bundle / filename
        obj = json.loads(path.read_text('utf-8'))
        change(obj)
        write(path, obj)

    def test_valid_bundle_with_source(self):
        r = audit(self.bundle, self.video)
        self.assertEqual(r['audit_status'], 'bundle_integrity_verified_only')
        self.assertTrue(r['source_video_hash_checked'])
        self.assertFalse(r['ready_for_equity_or_ev'])

    def test_valid_bundle_without_source(self):
        self.assertFalse(audit(self.bundle)['source_video_hash_checked'])

    def test_cli(self):
        script = Path(__file__).with_name('offline_clip_artifact_audit.py')
        result = subprocess.run([sys.executable, str(script), str(self.bundle),
                                 '--source-video', str(self.video)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['source_video_hash_checked'])

    def test_clip_byte_tamper(self):
        with (self.bundle / 'clip.mp4').open('ab') as f: f.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): audit(self.bundle)

    def test_request_tamper(self):
        self.mutate('gate/request.json', lambda x: x.update(start_seconds=0))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): audit(self.bundle)

    def test_provenance_tamper(self):
        self.mutate('gate/provenance.json', lambda x: x.update(hand_id='H2'))
        with self.assertRaises(ValueError): audit(self.bundle)

    def test_sidecar_tamper(self):
        self.mutate('clip.mp4.json', lambda x: x.update(table_id=3))
        with self.assertRaises(ValueError): audit(self.bundle)

    def test_manifest_claims_equity(self):
        self.mutate('manifest.json', lambda x: x.update(ready_for_equity_or_ev=True))
        with self.assertRaisesRegex(ValueError, 'unverified analysis'): audit(self.bundle)

    def test_manifest_claims_ocr_source_link(self):
        self.mutate('manifest.json', lambda x: x.update(source_video_matches_ocr_source_verified=True))
        with self.assertRaisesRegex(ValueError, 'unverified analysis'): audit(self.bundle)

    def test_wrong_source_video(self):
        other = Path(self.tmp2.name) / 'other.mp4'
        other.write_bytes(b'not the source')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): audit(self.bundle, other)

    def test_missing_file(self):
        (self.bundle / 'gate/provenance.json').unlink()
        with self.assertRaisesRegex(ValueError, 'missing or unsafe'): audit(self.bundle)

    def test_symlink_clip(self):
        clip = self.bundle / 'clip.mp4'
        other = Path(self.tmp2.name) / 'original_clip.mp4'
        shutil.copy2(clip, other)
        clip.unlink()
        clip.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'missing or unsafe'): audit(self.bundle)

    def test_duplicate_json_keys(self):
        (self.bundle / 'manifest.json').write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): audit(self.bundle)

    def test_manifest_media_duration_tamper(self):
        self.mutate('manifest.json', lambda x: x.update(clip_duration_seconds=99))
        with self.assertRaisesRegex(ValueError, 'clip media mismatch'): audit(self.bundle)

    def test_sidecar_unverified_flag_flip(self):
        self.mutate('clip.mp4.json', lambda x: x.update(video_evidence_verified=True))
        with self.assertRaisesRegex(ValueError, 'unverified analysis'): audit(self.bundle)

    def test_source_symlink(self):
        link = Path(self.tmp2.name) / 'source_link.mp4'
        link.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, 'unsafe source video'): audit(self.bundle, link)


if __name__ == '__main__':
    unittest.main()
