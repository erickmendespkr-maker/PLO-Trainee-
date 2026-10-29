"""Real FFmpeg integration tests, using only artificial recordings and review records."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_clip_review_gate import sha
from offline_reviewed_clip_pipeline import run


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.video_dir = tempfile.TemporaryDirectory()
        cls.video = Path(cls.video_dir.name) / 'recording.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=10:duration=4',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
                        '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(cls.video)],
                       check=True, capture_output=True, timeout=40)

    @classmethod
    def tearDownClass(cls):
        cls.video_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.drafts, self.review, self.crop, self.out = (
            self.root / 'drafts.json', self.root / 'review.json',
            self.root / 'crop.json', self.root / 'result')
        self.d = {'schema_version': 1, 'analysis_status': 'offline_reviewed_hand_drafts_only',
                  'source_reviewed_report_sha256': 'a' * 64,
                  'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
                  'hands': [{'hand_id': 'H1', 'table_id': 4, 'variant': 'PLO6',
                             'start_seconds': 1, 'end_seconds': 3,
                             'boundary_origin': 'manual_unverified',
                             'status': 'draft_requires_human_reconstruction',
                             'ready_for_equity_or_ev': False}]}
        self.write(self.drafts, self.d)
        self.r = {'schema_version': 1, 'analysis_status': 'offline_boundary_review_import_only',
                  'source_hand_drafts_sha256': sha(self.drafts),
                  'source_reviewed_report_sha256': 'a' * 64,
                  'ready_for_equity_or_ev': False,
                  'reviewed_boundaries_are_poker_verified': False,
                  'annotations': [{'hand_id': 'H1', 'table_id': 4, 'review_status': 'confirmed',
                                   'changed': False, 'review_note': '',
                                   'source_start_seconds': 1, 'source_end_seconds': 3,
                                   'revised_start_seconds': 1, 'revised_end_seconds': 3}]}
        self.write(self.review, self.r)
        self.write(self.crop, {'x': 160, 'y': 0, 'width': 160, 'height': 120})

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value) + '\n', 'utf-8')

    def pipeline(self):
        return run(self.video, self.drafts, self.review, 'H1', self.crop, self.out)

    def test_real_ffmpeg_end_to_end_and_hashes(self):
        manifest = self.pipeline()
        self.assertEqual(manifest['clip_dimensions'], {'width': 160, 'height': 120})
        self.assertAlmostEqual(manifest['clip_duration_seconds'], 2, delta=.25)
        self.assertEqual(manifest['clip_sha256'], sha(self.out / 'clip.mp4'))
        self.assertEqual(manifest['gate_request_sha256'], sha(self.out / 'gate' / 'request.json'))
        self.assertEqual(manifest['gate_provenance_sha256'], sha(self.out / 'gate' / 'provenance.json'))
        self.assertEqual(manifest['clip_sidecar_sha256'], sha(self.out / 'clip.mp4.json'))
        self.assertFalse(manifest['ready_for_equity_or_ev'])
        self.assertFalse(manifest['source_video_matches_ocr_source_verified'])
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text()), manifest)
        self.assertEqual(sha(self.video), manifest['source_video_sha256'])

    def test_corrected_review_integrates(self):
        a = self.r['annotations'][0]
        a.update(review_status='corrected', changed=True, review_note='human correction',
                 revised_start_seconds=1.5, revised_end_seconds=2.5)
        self.write(self.review, self.r)
        manifest = self.pipeline()
        self.assertAlmostEqual(manifest['clip_duration_seconds'], 1, delta=.25)
        self.assertEqual(json.loads((self.out / 'gate' / 'request.json').read_text())['start_seconds'], 1.5)

    def test_pending_review_blocks_without_output(self):
        self.r['annotations'][0]['review_status'] = 'pending'
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.pipeline()
        self.assertFalse(self.out.exists())

    def test_existing_destination_not_overwritten(self):
        self.out.mkdir()
        (self.out / 'keep.txt').write_text('keep')
        with self.assertRaises(ValueError): self.pipeline()
        self.assertEqual((self.out / 'keep.txt').read_text(), 'keep')

    def test_invalid_crop_blocks_without_output(self):
        self.write(self.crop, {'x': 300, 'y': 0, 'width': 160, 'height': 120})
        with self.assertRaises(ValueError): self.pipeline()
        self.assertFalse(self.out.exists())

    def test_stale_draft_hash_blocks(self):
        self.d['hands'][0]['variant'] = 'PLO5'
        self.write(self.drafts, self.d)
        with self.assertRaises(ValueError): self.pipeline()
        self.assertFalse(self.out.exists())

    def test_missing_hand_blocks(self):
        with self.assertRaises(ValueError):
            run(self.video, self.drafts, self.review, 'H2', self.crop, self.out)
        self.assertFalse(self.out.exists())

    def test_symlink_review_blocks(self):
        link = self.root / 'linked.json'
        link.symlink_to(self.review)
        with self.assertRaises(ValueError):
            run(self.video, self.drafts, link, 'H1', self.crop, self.out)
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
