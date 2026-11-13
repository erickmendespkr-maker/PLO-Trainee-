"""Synthetic integration tests for the existing real FFmpeg/FFprobe auditors."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_clip_audit_bundle import audit_clip_bundle
from offline_clip_evidence_manifest import clip_sha256


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clip = Path(self.temp.name) / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=96x64:rate=10:duration=2', '-c:v', 'mpeg4',
                        '-y', str(self.clip)], check=True)
        self.manifest = {'status': 'PENDING_INDEPENDENT_AUDIT',
                         'approved_for_publication': False,
                         'clip': {'sha256': clip_sha256(self.clip), 'start_seconds': 10, 'end_seconds': 12}}

    def test_valid_clip_is_still_unapproved(self):
        result = audit_clip_bundle(self.manifest, self.clip)
        self.assertEqual(result['status'], 'TECHNICAL_CLIP_AUDITS_PASSED_ONLY')
        self.assertEqual(result['pts_audit']['frame_count'], 20)
        for key in ('approved_for_publication', 'source_timeline_verified', 'visual_hand_verified', 'ev_verified'):
            self.assertIs(result[key], False)

    def test_tampered_file_rejected(self):
        self.clip.write_bytes(self.clip.read_bytes() + b'altered')
        with self.assertRaises(ValueError):
            audit_clip_bundle(self.manifest, self.clip)

    def test_wrong_interval_rejected(self):
        self.manifest['clip']['end_seconds'] = 14
        with self.assertRaises(ValueError):
            audit_clip_bundle(self.manifest, self.clip)

    def test_symlink_rejected(self):
        link = Path(self.temp.name) / 'link.mp4'
        link.symlink_to(self.clip)
        with self.assertRaises(ValueError):
            audit_clip_bundle(self.manifest, link)

    def test_pts_failure_propagates(self):
        with patch('offline_clip_audit_bundle.audit_decoded_pts', side_effect=ValueError('PTS invalid')):
            with self.assertRaisesRegex(ValueError, 'PTS invalid'):
                audit_clip_bundle(self.manifest, self.clip)

    def test_audit_cannot_promote_publication(self):
        with patch('offline_clip_audit_bundle.audit_decoded_pts', return_value={'approved_for_publication': True}):
            with self.assertRaises(ValueError):
                audit_clip_bundle(self.manifest, self.clip)


if __name__ == '__main__':
    unittest.main()
