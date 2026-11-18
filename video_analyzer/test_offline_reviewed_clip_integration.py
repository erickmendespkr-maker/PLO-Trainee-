"""Synthetic end-to-end gate -> FFmpeg export regression tests; no real hands."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_reviewed_clip_gate import build_reviewed_clip_plan
from offline_reviewed_clip_executor import export_reviewed_clip


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and FFprobe required')
class ReviewedClipIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10', '-t', '3', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', str(self.video)], check=True, timeout=30)
        self.record = {'hand_id': 'synthetic-hand', 'table_id': 2, 'start_pts': .5,
                       'end_pts': 2.0, 'video_sha256': hashlib.sha256(self.video.read_bytes()).hexdigest(),
                       'human_reviewed': True, 'hand_boundary_confirmed': True,
                       'explanation_verified': True,
                       'explanation': 'Synthetic example only: conditional assumptions, not GTO.'}

    def test_gate_to_export_provenance(self):
        plan = build_reviewed_clip_plan(self.record, 3)
        output = self.root / 'cut.mp4'
        metadata = export_reviewed_clip(self.video, plan, output)
        self.assertEqual(metadata['plan_sha256'], plan['manifest_sha256'])
        self.assertEqual(metadata['source_sha256'], self.record['video_sha256'])
        self.assertEqual(metadata['clip_sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(json.loads(Path(str(output)+'.json').read_text()), metadata)
        self.assertEqual(metadata['table_id'], 2)
        self.assertAlmostEqual(metadata['clip_duration_seconds'], 1.5, delta=.2)
        self.assertTrue(metadata['not_gto'])

    def test_review_gate_blocks_unreviewed_export(self):
        for field in ('human_reviewed', 'hand_boundary_confirmed', 'explanation_verified'):
            with self.subTest(field=field):
                record = dict(self.record, **{field: False})
                plan = build_reviewed_clip_plan(record, 3)
                self.assertEqual(plan['status'], 'REVIEW_REQUIRED')
                with self.assertRaisesRegex(ValueError, 'human-reviewed'):
                    export_reviewed_clip(self.video, plan, self.root / (field + '.mp4'))

    def test_source_mutation_blocks_export(self):
        plan = build_reviewed_clip_plan(self.record, 3)
        self.video.write_bytes(self.video.read_bytes() + b'mutation')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            export_reviewed_clip(self.video, plan, self.root / 'cut.mp4')

    def test_clip_longer_than_executor_limit_rejected(self):
        record = dict(self.record, end_pts=181.5)
        plan = build_reviewed_clip_plan(record, 200)
        with self.assertRaisesRegex(ValueError, 'invalid clip timestamps'):
            export_reviewed_clip(self.video, plan, self.root / 'cut.mp4')

    def test_tampered_reviewed_explanation_rejected(self):
        plan = build_reviewed_clip_plan(self.record, 3)
        plan['explanation'] = 'A different explanation'
        with self.assertRaisesRegex(ValueError, 'modified clip plan'):
            export_reviewed_clip(self.video, plan, self.root / 'cut.mp4')


if __name__ == '__main__':
    unittest.main()
