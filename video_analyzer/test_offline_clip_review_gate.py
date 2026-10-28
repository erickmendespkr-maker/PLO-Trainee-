"""Offline synthetic tests for reviewed-boundary clip request gating."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from offline_clip_review_gate import prepare, load, sha


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_video = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp_video.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=10:duration=4',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)],
                       capture_output=True, timeout=30, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp_video.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.drafts, self.review, self.crop, self.output = (
            root / 'draft.json', root / 'review.json', root / 'crop.json', root / 'output')
        self.d = {'schema_version': 1, 'analysis_status': 'offline_reviewed_hand_drafts_only',
                  'source_reviewed_report_sha256': 'a' * 64,
                  'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
                  'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                             'start_seconds': 0, 'end_seconds': 2,
                             'boundary_origin': 'manual_unverified',
                             'status': 'draft_requires_human_reconstruction',
                             'ready_for_equity_or_ev': False}]}
        self.write(self.drafts, self.d)
        self.r = {'schema_version': 1, 'analysis_status': 'offline_boundary_review_import_only',
                  'source_hand_drafts_sha256': sha(self.drafts),
                  'source_reviewed_report_sha256': 'a' * 64,
                  'ready_for_equity_or_ev': False,
                  'reviewed_boundaries_are_poker_verified': False,
                  'annotations': [{'hand_id': 'H1', 'table_id': 1,
                                   'review_status': 'confirmed', 'changed': False,
                                   'review_note': '', 'source_start_seconds': 0,
                                   'source_end_seconds': 2,
                                   'revised_start_seconds': 0, 'revised_end_seconds': 2}]}
        self.c = {'x': 0, 'y': 0, 'width': 160, 'height': 120}
        self.write(self.review, self.r)
        self.write(self.crop, self.c)

    @staticmethod
    def write(path, obj):
        path.write_text(json.dumps(obj) + '\n', 'utf-8')

    def gate(self, hand_id='H1'):
        return prepare(self.video, self.drafts, self.review, hand_id, self.crop, self.output)

    def test_valid_request_and_provenance(self):
        request, provenance = self.gate()
        self.assertEqual(request['start_seconds'], 0)
        self.assertEqual(request['end_seconds'], 2)
        self.assertEqual(request['source_video_sha256'], sha(self.video))
        self.assertTrue(request['reviewer_confirmed_offline'])
        self.assertFalse(provenance['ready_for_equity_or_ev'])
        self.assertFalse(provenance['source_video_matches_ocr_source_verified'])
        self.assertEqual(load(self.output / 'request.json'), request)
        self.assertEqual(load(self.output / 'provenance.json'), provenance)

    def test_corrected_bounds(self):
        a = self.r['annotations'][0]
        a.update(review_status='corrected', changed=True, review_note='Manual change',
                 revised_start_seconds=0.5, revised_end_seconds=2.5)
        self.write(self.review, self.r)
        request, _ = self.gate()
        self.assertEqual((request['start_seconds'], request['end_seconds']), (0.5, 2.5))

    def test_pending_not_exportable(self):
        self.r['annotations'][0]['review_status'] = 'pending'
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.gate()
        self.assertFalse(self.output.exists())

    def test_inconclusive_not_exportable(self):
        self.r['annotations'][0]['review_status'] = 'inconclusive'
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.gate()

    def test_invalid_correction_without_note(self):
        self.r['annotations'][0].update(review_status='corrected', changed=True,
                                        revised_start_seconds=.5)
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.gate()

    def test_stale_draft_sha(self):
        self.d['hands'][0]['variant'] = 'PLO6'
        self.write(self.drafts, self.d)
        with self.assertRaises(ValueError): self.gate()

    def test_wrong_table(self):
        self.r['annotations'][0]['table_id'] = 4
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.gate()

    def test_crop_outside_video(self):
        self.c['x'] = 200
        self.write(self.crop, self.c)
        with self.assertRaises(ValueError): self.gate()

    def test_odd_crop(self):
        self.c['width'] = 159
        self.write(self.crop, self.c)
        with self.assertRaises(ValueError): self.gate()

    def test_extra_crop_field(self):
        self.c['auto_crop'] = True
        self.write(self.crop, self.c)
        with self.assertRaises(ValueError): self.gate()

    def test_missing_hand(self):
        with self.assertRaises(ValueError): self.gate('missing')

    def test_duplicate_json_key(self):
        self.crop.write_text('{"x":0,"x":0}', 'utf-8')
        with self.assertRaises(ValueError): self.gate()

    def test_nonfinite_json(self):
        self.crop.write_text('{"x":NaN}', 'utf-8')
        with self.assertRaises(ValueError): self.gate()

    def test_symlink_review(self):
        link = self.review.parent / 'link.json'
        link.symlink_to(self.review)
        with self.assertRaises(ValueError):
            prepare(self.video, self.drafts, link, 'H1', self.crop, self.output)

    def test_existing_output_not_overwritten(self):
        self.output.mkdir()
        with self.assertRaises(ValueError): self.gate()
        self.assertTrue(self.output.exists())

    def test_outside_video(self):
        self.r['annotations'][0].update(review_status='corrected', changed=True,
                 review_note='out of video', revised_end_seconds=5)
        self.write(self.review, self.r)
        with self.assertRaises(ValueError): self.gate()


if __name__ == '__main__':
    unittest.main()
