"""Synthetic FFmpeg smoke tests for offline review clip export."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
try:
    from .offline_review_clip_export import ClipExportError, export_review_clip
except ImportError:
    from offline_review_clip_export import ClipExportError, export_review_clip

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=160x90:r=10:d=3', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-y', str(self.source)], check=True)
        self.record = dict(start_pts=0.5, end_pts=1.5, table_id=1)

    def test_export_and_sidecar_sha(self):
        dst = self.root / 'review.mp4'
        result = export_review_clip(self.source, dst, self.record)
        sidecar = json.loads(dst.with_suffix('.json').read_text())
        self.assertEqual(result, sidecar)
        self.assertEqual(sidecar['clip_sha256'], hashlib.sha256(dst.read_bytes()).hexdigest())
        self.assertEqual(sidecar['evidence_gate']['status'], 'REVIEW_REQUIRED')
        self.assertFalse(sidecar['evidence_gate']['can_label_error'])
        self.assertFalse(sidecar['gto_solution'])
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                         'format=duration', '-of', 'default=nw=1:nk=1', str(dst)])
        self.assertAlmostEqual(float(probe), 1.0, delta=0.2)

    def test_reject_out_of_bounds(self):
        with self.assertRaises(ClipExportError):
            export_review_clip(self.source, self.root / 'bad.mp4',
                               {**self.record, 'end_pts': 5})

    def test_reject_overwrite(self):
        dst = self.root / 'review.mp4'
        export_review_clip(self.source, dst, self.record)
        with self.assertRaises(ClipExportError):
            export_review_clip(self.source, dst, self.record)

    def test_reject_same_source(self):
        with self.assertRaises(ClipExportError):
            export_review_clip(self.source, self.source, self.record)

    def test_invalid_gate(self):
        with self.assertRaises(ValueError):
            export_review_clip(self.source, self.root / 'bad.mp4',
                               {**self.record, 'table_id': 5})

    def test_no_hand_claim_even_with_verified_flags(self):
        dst = self.root / 'verified.mp4'
        record = {**self.record, **dict.fromkeys((
            'table_verified', 'hand_verified', 'hero_cards_verified',
            'board_verified', 'action_verified', 'amounts_verified'), True),
            'ev_assumptions': {'ranges': 'hypothetical', 'rake': 'zero', 'future_actions': 'none'}}
        result = export_review_clip(self.source, dst, record)
        self.assertEqual(result['evidence_gate']['status'], 'APPROVED_CONDITIONAL')
        self.assertFalse(result['evidence_gate']['can_label_error'])
        self.assertFalse(result['human_review_of_export'])

if __name__ == '__main__':
    unittest.main()
