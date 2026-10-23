"""Synthetic, offline FFmpeg and HTML preview tests; no poker-video accuracy claims."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from activity_clip_region_preview import build_region_preview
from activity_clip_selection_editor import render_clip_selection_editor, main
from activity_review_clip_template import build_clip_selection_template
import test_activity_review_clip_export as fixtures


class ClipRegionPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.NeutralReviewClipsTests.setUpClass()
        cls.f = fixtures.NeutralReviewClipsTests
        cls.template = build_clip_selection_template(cls.f.video, cls.f.queue, cls.f.draft)

    @classmethod
    def tearDownClass(cls):
        fixtures.NeutralReviewClipsTests.tearDownClass()

    def test_ffmpeg_preview_is_bounded_and_pinned_to_video(self):
        original = copy.deepcopy(self.template)
        preview = build_region_preview(self.f.video, self.template)
        self.assertEqual(self.template, original)
        self.assertEqual(preview['recording_sha256'], self.template['recording_sha256'])
        self.assertEqual((preview['source_width'], preview['source_height']), (160, 120))
        jpeg = base64.b64decode(preview['jpeg_b64'])
        self.assertEqual(hashlib.sha256(jpeg).hexdigest(), preview['jpeg_sha256'])
        self.assertTrue(jpeg.startswith(b'\xff\xd8'))
        self.assertTrue(jpeg.endswith(b'\xff\xd9'))
        html = render_clip_selection_editor(self.template, preview=preview)
        self.assertIn('id="preview-frame"', html)
        self.assertIn('id="region-overlay"', html)
        self.assertIn("img-src data:", html)
        self.assertIn('Quadro aproximado', html)
        self.assertNotIn('https://', html)
        self.assertIn('confirmRegions.checked = false', html)
        self.assertIn('ready_for_equity_or_ev', json.dumps(self.f.draft))

    def test_wrong_recording_rejected_before_ffmpeg(self):
        bad = copy.deepcopy(self.template)
        bad['recording_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_region_preview(self.f.video, bad)

    def test_timestamp_bounds_and_types(self):
        for value in (-1, 4, float('nan'), float('inf'), True, '1.0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_region_preview(self.f.video, self.template, timestamp=value)

    def test_valid_explicit_timestamp(self):
        preview = build_region_preview(self.f.video, self.template, timestamp=1)
        self.assertEqual(preview['requested_timestamp_seconds'], 1.0)

    def test_preview_binding_and_integrity_rejections(self):
        preview = build_region_preview(self.f.video, self.template)
        cases = [
            ('recording_sha256', '0'*64),
            ('jpeg_sha256', '0'*64),
            ('jpeg_b64', '<script>alert(1)</script>'),
            ('jpeg_b64', 'A'*3000000),
            ('source_width', 0),
            ('source_height', True),
            ('requested_timestamp_seconds', float('nan')),
            ('frame_timing', 'verified_poker_action'),
        ]
        for key, value in cases:
            changed = dict(preview); changed[key] = value
            with self.subTest(key=key, value=str(value)[:25]), self.assertRaises(ValueError):
                render_clip_selection_editor(self.template, preview=changed)
        changed = dict(preview); changed['unexpected'] = 1
        with self.assertRaises(ValueError): render_clip_selection_editor(self.template, preview=changed)

    def test_cli_creates_new_self_contained_html(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, output = root/'template.json', root/'editor.html'
            source.write_text(json.dumps(self.template), encoding='utf-8')
            self.assertEqual(main([str(source), str(output), '--video', str(self.f.video),
                                   '--timestamp', '1.0']), 0)
            self.assertIn('data:image/jpeg;base64,', output.read_text(encoding='utf-8'))
            with self.assertRaises(ValueError):
                main([str(source), str(output), '--video', str(self.f.video)])
            with self.assertRaises(ValueError):
                main([str(source), str(root/'another.html'), '--timestamp', '1'])

    def test_no_preview_default_is_still_offline_and_unapproved(self):
        html = render_clip_selection_editor(self.template)
        self.assertNotIn('id="preview-frame"', html)
        self.assertNotIn('data:image/jpeg', html)
        self.assertIn('Confirme manualmente', html)


if __name__ == '__main__':
    unittest.main()
