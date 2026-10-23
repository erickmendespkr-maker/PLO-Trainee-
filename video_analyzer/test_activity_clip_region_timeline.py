"""Synthetic timeline preview checks; no claims about real poker OCR or PTS."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from activity_clip_region_timeline import build_region_preview_timeline
from activity_clip_selection_editor import main, render_clip_selection_editor
from activity_review_clip_template import build_clip_selection_template
import test_activity_review_clip_export as fixtures


class TimelinePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.NeutralReviewClipsTests.setUpClass()
        cls.f = fixtures.NeutralReviewClipsTests
        cls.template = build_clip_selection_template(cls.f.video, cls.f.queue, cls.f.draft)

    @classmethod
    def tearDownClass(cls):
        fixtures.NeutralReviewClipsTests.tearDownClass()

    def test_three_frames_bound_to_original_and_html_offline(self):
        template = copy.deepcopy(self.template)
        timeline = build_region_preview_timeline(self.f.video, template)
        self.assertEqual(template, self.template)
        self.assertEqual(len(timeline['frames']), 3)
        self.assertEqual(timeline['recording_sha256'], self.template['recording_sha256'])
        self.assertEqual([round(f['requested_timestamp_seconds'], 1) for f in timeline['frames']],
                         [0.4, 2.0, 3.6])
        for frame in timeline['frames']:
            data = base64.b64decode(frame['jpeg_b64'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), frame['jpeg_sha256'])
            self.assertTrue(data.startswith(b'\xff\xd8'))
            self.assertTrue(data.endswith(b'\xff\xd9'))
            self.assertEqual(frame['frame_timing'], 'approximate_ffmpeg_fast_seek_not_decision_evidence')
        html = render_clip_selection_editor(template, preview_timeline=timeline)
        self.assertIn('id="frame-prev"', html)
        self.assertIn('id="frame-next"', html)
        self.assertIn('id="frame-reviewed"', html)
        self.assertIn('reviewedFrames.size !== timelineFrames.length', html)
        self.assertIn('reviewedFrames.clear()', html)
        self.assertNotIn('https://', html)
        self.assertIn('Content-Security-Policy', html)
        self.assertIn('ready_for_equity_or_ev', json.dumps(self.f.draft))

    def test_explicit_sorted_timestamps(self):
        timeline = build_region_preview_timeline(self.f.video, self.template, timestamps=[0, .5, 1.5, 1.9])
        self.assertEqual(len(timeline['frames']), 4)
        self.assertEqual(timeline['frames'][0]['requested_timestamp_seconds'], 0.0)

    def test_bad_timestamps_rejected(self):
        bad = [[0], [0, .5, 1, 1.5, 1.8, 1.9], [0, 0], [1, .5], [-1, .5],
               [0, 4], [0, float('nan')], [0, float('inf')], [0, True],
               [0, '1'], '0,1']
        for times in bad:
            with self.subTest(times=times), self.assertRaises(ValueError):
                build_region_preview_timeline(self.f.video, self.template, timestamps=times)

    def test_recording_mismatch_rejected(self):
        template = copy.deepcopy(self.template)
        template['recording_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_region_preview_timeline(self.f.video, template)

    def test_timeline_schema_and_integrity_rejections(self):
        valid = build_region_preview_timeline(self.f.video, self.template)
        cases = []
        wrong = copy.deepcopy(valid); wrong['recording_sha256'] = '0'*64; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['schema_version'] = True; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['extra'] = 'unsafe'; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'].reverse(); cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'][1]['jpeg_sha256'] = '0'*64; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'][1]['source_width'] += 1; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'][1]['frame_timing'] = 'verified_action'; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'][1]['jpeg_b64'] = '<script>alert(1)</script>'; cases.append(wrong)
        wrong = copy.deepcopy(valid); wrong['frames'] = wrong['frames'][:1]; cases.append(wrong)
        for case in cases:
            with self.subTest(case=str(case)[:90]), self.assertRaises(ValueError):
                render_clip_selection_editor(self.template, preview_timeline=case)
        with self.assertRaises(ValueError):
            render_clip_selection_editor(self.template, preview=valid['frames'][0], preview_timeline=valid)

    def test_cli_timeline_creates_only_new_html(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)/'template.json'
            dest = Path(td)/'timeline.html'
            src.write_text(json.dumps(self.template), encoding='utf-8')
            self.assertEqual(main([str(src), str(dest), '--video', str(self.f.video), '--timeline']), 0)
            self.assertIn('Quadro anterior', dest.read_text(encoding='utf-8'))
            with self.assertRaises(ValueError):
                main([str(src), str(dest), '--video', str(self.f.video), '--timeline'])
            with self.assertRaises(ValueError):
                main([str(src), str(Path(td)/'a.html'), '--timeline'])
            with self.assertRaises(ValueError):
                main([str(src), str(Path(td)/'b.html'), '--video', str(self.f.video),
                      '--timeline', '--timestamp', '1'])


if __name__ == '__main__':
    unittest.main()
