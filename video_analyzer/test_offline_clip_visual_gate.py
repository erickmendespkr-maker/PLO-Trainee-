import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import offline_clip_visual_gate as gate


class VisualGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.src = Path(self.temp.name) / 'source.mp4'
        self.src.write_bytes(b'source')
        self.clip = Path(self.temp.name) / 'clip.mp4'
        self.clip.write_bytes(b'clip')
        self.technical = {'status': 'TECHNICAL_CLIP_AUDITS_PASSED_ONLY',
                          'approved_for_publication': False,
                          'pts_audit': {'frame_count': 2}}
        self.visual = {'status': 'EXACT_DECODED_FRAMES_MATCH',
                       'approved_for_publication': False,
                       'visual_hand_verified': False,
                       'clip_frames': 2, 'matching_frames': 2, 'mismatch_count': 0}

    def run_gate(self):
        with patch.object(gate, 'audit_clip_bundle', return_value=self.technical), patch.object(gate, 'audit_exact_frames', return_value=self.visual):
            return gate.audit_visual_gate({}, self.src, self.clip, source_first_frame=3)

    def test_match_remains_unapproved(self):
        result = self.run_gate()
        self.assertEqual(result['status'], 'PIXEL_AND_TECHNICAL_CANDIDATE_ONLY')
        self.assertFalse(result['approved_for_publication'])

    def test_mismatch(self):
        self.visual.update(status='FRAME_CONTENT_MISMATCH', matching_frames=1, mismatch_count=1)
        self.assertEqual(self.run_gate()['status'], 'FRAME_CONTENT_MISMATCH')

    def test_mismatched_count(self):
        self.technical['pts_audit']['frame_count'] = 3
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_inconsistent_pixel_counts(self):
        self.visual['matching_frames'] = 1
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_unexpected_approval(self):
        self.visual['approved_for_publication'] = True
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_invalid_technical_status(self):
        self.technical['status'] = 'ERROR'
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_status_count_disagreement(self):
        self.visual['status'] = 'FRAME_CONTENT_MISMATCH'
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_missing_file(self):
        self.src.unlink()
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_bool_index(self):
        with self.assertRaises(ValueError):
            gate.audit_visual_gate({}, self.src, self.clip, source_first_frame=True)

    def test_symlink_rejected(self):
        self.clip.unlink()
        self.clip.symlink_to(self.src)
        with self.assertRaises(ValueError):
            self.run_gate()


if __name__ == '__main__':
    unittest.main()
