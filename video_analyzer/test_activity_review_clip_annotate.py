"""Real FFmpeg end-card tests using only synthetic four-table footage."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from activity_review_clip_annotate import (
    OUTPUT_STATUS, _caption, _validate_manifest, annotate_review_clips,
)
from activity_review_clip_export import export_review_clips
import test_activity_review_clip_export as fixture_module


class ReviewEndCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.NeutralReviewClipsTests.setUpClass()
        cls.fixture = fixture_module.NeutralReviewClipsTests
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name, data in [('queue', cls.fixture.queue), ('draft', cls.fixture.draft),
                           ('selection', cls.fixture.selection)]:
            (cls.root / f'{name}.json').write_text(json.dumps(data), encoding='utf-8')
        cls.originals = cls.root / 'originals'
        cls.manifest = export_review_clips(
            cls.fixture.video, cls.root/'queue.json', cls.root/'draft.json',
            cls.root/'selection.json', cls.originals)
        cls.manifest_path = cls.originals / 'review_clip_manifest.json'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        fixture_module.NeutralReviewClipsTests.tearDownClass()

    def test_four_table_end_cards_are_real_mp4s_and_auditable(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'annotated'
            result = annotate_review_clips(self.manifest_path, self.originals, out)
            self.assertEqual(result['analysis_status'], OUTPUT_STATUS)
            self.assertEqual(result['clips_generated'], 4)
            self.assertFalse(result['ready_for_equity_or_ev'])
            self.assertFalse(result['source_visual_content_verified'])
            self.assertEqual(json.loads((out/'annotated_clip_manifest.json').read_text()), result)
            for clip in result['clips']:
                annotated = out / clip['filename']
                self.assertTrue(annotated.is_file())
                self.assertEqual(hashlib.sha256(annotated.read_bytes()).hexdigest(),
                                 clip['annotated_mp4_sha256'])
                self.assertEqual(clip['decoded_output']['width'], 960)
                self.assertEqual(clip['decoded_output']['height'], 540)
                self.assertGreater(clip['decoded_output']['duration'], 4)
                self.assertEqual(clip['annotation_type'], 'separate_human_review_end_card')
            # Decode a frame from the end card. Text produces bright pixels on dark slate.
            clip = out / result['clips'][0]['filename']
            frame = subprocess.run(
                ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                 '-ss', '3', '-i', str(clip), '-frames:v', '1', '-f', 'rawvideo',
                 '-pix_fmt', 'gray', 'pipe:1'], check=True, capture_output=True).stdout
            self.assertEqual(len(frame), 960*540)
            self.assertGreater(sum(value > 160 for value in frame), 100)

    def test_end_card_explicitly_disclaims_strategic_accuracy(self):
        caption = _caption(self.manifest['clips'][0])
        self.assertIn('SEM CONCLUSÃO DE ERRO', caption)
        self.assertIn('NÃO verificados', caption)
        self.assertIn('Revisão humana', caption)

    def test_untrusted_text_cannot_add_ffmpeg_filter(self):
        clip = copy.deepcopy(self.manifest['clips'][0])
        clip['explanation'] = '%{metadata\\:title}: x;drawtext=malicious'
        self.assertIn('%{metadata', _caption(clip))
        self.assertIn('expansion=none', __import__('inspect').getsource(
            __import__('activity_review_clip_annotate')._render_card_clip))

    def test_rejects_control_characters_and_overlong_explanation(self):
        for value in ('bad\x00caption', 'bidi\u202eoverride', 'x'*701, ''):
            clip = copy.deepcopy(self.manifest['clips'][0]); clip['explanation'] = value
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                _caption(clip)

    def test_rejects_ev_claims_or_verified_visual_status(self):
        for key, value in [('ready_for_equity_or_ev', True),
                           ('authorized_for_ev_based_ranking', True),
                           ('source_visual_content_verified', True),
                           ('analysis_status', 'real_money_error_detected')]:
            obj = copy.deepcopy(self.manifest); obj[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                _validate_manifest(obj, self.originals)

    def test_rejects_path_traversal_and_duplicate_filename(self):
        obj = copy.deepcopy(self.manifest)
        obj['clips'][0]['filename'] = '../other.mp4'
        with self.assertRaisesRegex(ValueError, 'filename'):
            _validate_manifest(obj, self.originals)
        obj = copy.deepcopy(self.manifest)
        obj['clips'][1]['filename'] = obj['clips'][0]['filename']
        with self.assertRaisesRegex(ValueError, 'filename'):
            _validate_manifest(obj, self.originals)

    def test_rejects_preexisting_or_nested_output(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'output'):
                annotate_review_clips(self.manifest_path, self.originals, td)
        with self.assertRaisesRegex(ValueError, 'output'):
            annotate_review_clips(self.manifest_path, self.originals,
                                  self.originals / 'annotated')

    def test_rejects_symlinked_original_video(self):
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td)
            for clip in self.manifest['clips']:
                (dst / clip['filename']).symlink_to(self.originals / clip['filename'])
            with self.assertRaisesRegex(ValueError, 'symlinked'):
                _validate_manifest(self.manifest, dst)

    def test_rejects_tampered_original_video(self):
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td)
            for clip in self.manifest['clips']:
                shutil.copy2(self.originals / clip['filename'], dst / clip['filename'])
            with (dst / self.manifest['clips'][0]['filename']).open('ab') as handle:
                handle.write(b'tamper')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                _validate_manifest(self.manifest, dst)

    def test_atomic_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'never_created'
            with patch('activity_review_clip_annotate._render_card_clip',
                       side_effect=ValueError('FFmpeg failure')):
                with self.assertRaisesRegex(ValueError, 'FFmpeg failure'):
                    annotate_review_clips(self.manifest_path, self.originals, output)
            self.assertFalse(output.exists())
            self.assertTrue(self.manifest_path.exists())

    def test_rejects_bad_duration_and_metadata(self):
        for field, value in [('duration', -1), ('width', 12345)]:
            obj = copy.deepcopy(self.manifest)
            obj['clips'][0]['decoded_output'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                _validate_manifest(obj, self.originals)


if __name__ == '__main__':
    unittest.main()
