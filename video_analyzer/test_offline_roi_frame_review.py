"""Synthetic-only tests of offline multi-timestamp ROI review; no real poker recognition."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import offline_roi_frame_review as review
import offline_reviewed_hand_math_queue as queue
from test_offline_ffmpeg_tesseract_proposals import ExtractorTests
from test_offline_table_roi_sampler import template


def selection():
    return {'schema_version': 1, 'status': review.STATUS,
            'frames': [{'hand_id': 'H1', 'pts_seconds': 1.0},
                       {'hand_id': 'H2', 'pts_seconds': 2.0}]}


class FrameReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ExtractorTests.setUpClass()
        cls.video, cls.plan, cls.plan_path = (ExtractorTests.video,
                                               ExtractorTests.plan,
                                               ExtractorTests.plan_path)

    @classmethod
    def tearDownClass(cls):
        ExtractorTests.tearDownClass()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tpl_path = self.root / 'template.json'
        self.tpl_path.write_text(json.dumps(template()), encoding='utf-8')
        self.frames_path = self.root / 'frames.json'
        self.frames_path.write_text(json.dumps(selection()), encoding='utf-8')
        self.output = self.root / 'review'

    def tearDown(self):
        self.temp.cleanup()

    def run_generation(self):
        return review.generate(self.video, self.plan_path, self.tpl_path,
                               self.frames_path, self.output)

    def test_end_to_end_ffmpeg_two_editors_and_hashes(self):
        manifest = self.run_generation()
        self.assertEqual(len(manifest['frames']), 2)
        self.assertFalse(manifest['ocr_confirmed'])
        self.assertFalse(manifest['tracking_performed'])
        self.assertEqual(manifest['eligible_for_equity'], 0)
        self.assertTrue(manifest['manual_review_required'])
        self.assertEqual(manifest['source_video_sha256'], queue.digest(self.video))
        self.assertEqual(manifest['index_sha256'], queue.digest(self.output / 'index.html'))
        for row in manifest['frames']:
            png, page = self.output / row['frame'], self.output / row['editor']
            self.assertEqual(queue.digest(png), row['frame_sha256'])
            self.assertEqual(queue.digest(page), row['editor_sha256'])
            with Image.open(png) as im:
                self.assertEqual(im.size, (1280, 720))
            self.assertIn('data:image/png;base64,', page.read_text())
        index = (self.output / 'index.html').read_text()
        self.assertIn('frame_001.html', index)
        self.assertIn('frame_002.html', index)
        self.assertIn("default-src 'none'", index)
        self.assertNotIn('https://', index)

    def test_cli_and_refuses_overwrite(self):
        args = [str(self.video), str(self.plan_path), str(self.tpl_path),
                str(self.frames_path), str(self.output)]
        self.assertEqual(review.main(args), 0)
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            review.main(args)

    def test_rejects_outside_hand(self):
        spec = selection(); spec['frames'][0]['pts_seconds'] = .1
        with self.assertRaisesRegex(ValueError, 'outside reviewed'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_at_hand_end(self):
        spec = selection(); spec['frames'][0]['pts_seconds'] = 2.5
        with self.assertRaisesRegex(ValueError, 'outside reviewed'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_unknown_hand(self):
        spec = selection(); spec['frames'][0]['hand_id'] = 'H999'
        with self.assertRaisesRegex(ValueError, 'invalid hand'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_duplicate_selection(self):
        spec = selection(); spec['frames'].append(copy.deepcopy(spec['frames'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_more_than_twelve(self):
        spec = selection(); spec['frames'] = [dict(hand_id='H1', pts_seconds=1+i*.01)
                                              for i in range(13)]
        with self.assertRaisesRegex(ValueError, 'invalid frame'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_bool_timestamp(self):
        spec = selection(); spec['frames'][0]['pts_seconds'] = True
        with self.assertRaisesRegex(ValueError, 'invalid hand'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_nan_timestamp(self):
        spec = selection(); spec['frames'][0]['pts_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'invalid hand'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_extra_keys(self):
        spec = selection(); spec['frames'][0]['confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'invalid hand'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_bad_status(self):
        spec = selection(); spec['status'] = 'confirmed'
        with self.assertRaisesRegex(ValueError, 'invalid frame'):
            review.validate_frames(spec, queue.validate_plan(self.plan), 3)

    def test_rejects_video_hash_mismatch_no_output(self):
        plan = copy.deepcopy(self.plan); plan['source_video_sha256'] = 'f'*64
        pp = self.root / 'different_plan.json'; pp.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            review.generate(self.video, pp, self.tpl_path, self.frames_path, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_invalid_template_no_output(self):
        tpl = template(); tpl['tables'][0]['roi']['x'] = .9
        self.tpl_path.write_text(json.dumps(tpl))
        with self.assertRaises(ValueError):
            self.run_generation()
        self.assertFalse(self.output.exists())

    def test_rejects_symlink_output(self):
        self.output.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            self.run_generation()

    def test_rejects_output_alias(self):
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            review.generate(self.video, self.plan_path, self.tpl_path,
                            self.frames_path, self.tpl_path)

    def test_cleanup_on_failed_ffmpeg(self):
        from unittest.mock import patch
        with patch.object(review.extractor, 'run', side_effect=ValueError('synthetic failure')):
            with self.assertRaisesRegex(ValueError, 'synthetic failure'):
                self.run_generation()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.plo_roi_frames_*')))

    def test_html_escape(self):
        page = review.index_page([{'hand_id':'<img src=x>', 'table_id':'T&1',
                                   'pts_seconds':1.0, 'frame':'frame.png', 'editor':'edit.html'}])
        self.assertIn('&lt;img src=x&gt;', page)
        self.assertIn('T&amp;1', page)
        self.assertNotIn('<img src=x>', page)


if __name__ == '__main__':
    unittest.main()
