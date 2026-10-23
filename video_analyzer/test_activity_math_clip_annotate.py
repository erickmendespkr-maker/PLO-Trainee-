"""Synthetic FFmpeg end-to-end tests for safe conditional-math MP4 end cards."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from activity_math_clip_annotate import (
    STATUS, CARD_SECONDS, _safe_lines, annotate_math_clips, main,
)
from test_activity_math_clip_context import MathClipContextTests


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class MathEndCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MathClipContextTests.setUpClass()
        cls.fx = MathClipContextTests
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.paths = []
        for name, obj in [('manifest', cls.fx.manifest), ('worksheet', cls.fx.worksheet),
                          ('request', cls.fx.request), ('report', cls.fx.report)]:
            path = cls.root / f'{name}.json'
            path.write_text(json.dumps(obj), encoding='utf-8')
            cls.paths.append(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.fx.tearDownClass()

    def run_export(self, target):
        return annotate_math_clips(self.paths[0], self.fx.clips_dir,
                                   self.paths[1], self.paths[2], self.paths[3], target)

    def test_four_real_mp4s_one_math_and_three_no_math(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'math_cards'
            result = self.run_export(target)
            self.assertEqual(result['analysis_status'], STATUS)
            self.assertEqual(result['clips_generated'], 4)
            self.assertEqual(sum(c['math_status'].startswith('conditional')
                                 for c in result['clips']), 1)
            self.assertFalse(result['authorized_for_ev_based_ranking'])
            self.assertFalse(result['source_visual_content_verified'])
            self.assertEqual(json.loads((target/'math_clip_manifest.json').read_text()), result)
            sidecar = json.loads((target/'math_explanations.json').read_text())
            self.assertEqual(len(sidecar['clips']), 4)
            for clip in result['clips']:
                path = target / clip['filename']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 clip['annotated_mp4_sha256'])
                self.assertEqual(clip['decoded_output']['width'], 960)
                self.assertEqual(clip['decoded_output']['height'], 540)
                self.assertGreater(clip['decoded_output']['duration'], CARD_SECONDS)
                self.assertFalse(clip['strategic_error_established'])
            # Decode one frame of the end card to prove pixels were rendered.
            path = target / result['clips'][0]['filename']
            decoded = subprocess.run(
                ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                 '-ss', '5', '-i', str(path), '-frames:v', '1', '-f', 'rawvideo',
                 '-pix_fmt', 'gray', 'pipe:1'], capture_output=True, check=True).stdout
            self.assertEqual(len(decoded), 960 * 540)
            self.assertGreater(sum(p > 160 for p in decoded), 100)

    def test_caption_preserves_uncertainty_and_no_math(self):
        from activity_math_explanation import build_explanations
        explanation = build_explanations(self.fx.manifest, self.fx.clips_dir,
                                         self.fx.worksheet, self.fx.request, self.fx.report)
        first, second = explanation['clips'][:2]
        self.assertIn('hipótese', _safe_lines(first))
        self.assertIn('NÃO é EV real', _safe_lines(first))
        self.assertIn('Sem cálculo', _safe_lines(second))
        self.assertIn('SEM DIAGNÓSTICO', _safe_lines(second))

    def test_tampered_report_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as td:
            report = json.loads(self.paths[3].read_text())
            report['results'][0]['equity'] = .42
            forged = Path(td)/'forged.json'
            forged.write_text(json.dumps(report))
            output = Path(td)/'out'
            with self.assertRaises(ValueError):
                annotate_math_clips(self.paths[0], self.fx.clips_dir,
                                    self.paths[1], self.paths[2], forged, output)
            self.assertFalse(output.exists())

    def test_tampered_mp4_fails(self):
        with tempfile.TemporaryDirectory() as td:
            clips = Path(td)/'clips'
            clips.mkdir()
            for item in self.fx.manifest['clips']:
                shutil.copy2(self.fx.clips_dir/item['filename'], clips/item['filename'])
            first = clips/self.fx.manifest['clips'][0]['filename']
            first.write_bytes(first.read_bytes() + b'forged')
            with self.assertRaises(ValueError):
                annotate_math_clips(self.paths[0], clips,
                                    self.paths[1], self.paths[2], self.paths[3], Path(td)/'out')

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'new'):
                self.run_export(Path(td))

    def test_rejects_output_nested_in_source_directory(self):
        with self.assertRaises(ValueError):
            self.run_export(self.fx.clips_dir / 'math_cards')

    def test_rejects_symlinked_json_input(self):
        with tempfile.TemporaryDirectory() as td:
            link = Path(td)/'linked.json'
            link.symlink_to(self.paths[0])
            with self.assertRaises(ValueError):
                annotate_math_clips(link, self.fx.clips_dir, self.paths[1],
                                    self.paths[2], self.paths[3], Path(td)/'out')

    def test_rejects_controls_and_bidi_in_display_text(self):
        for line in ('evil\x00text', 'evil\u202ereversed'):
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                _safe_lines({'display_card_lines': ['ok', 'ok', 'ok', line]})

    def test_ffmpeg_is_not_invoked_through_shell(self):
        import inspect
        from activity_math_clip_annotate import _render
        code = inspect.getsource(_render)
        self.assertIn('expansion=none', code)
        self.assertNotIn('shell=True', code)

    def test_cli_new_output_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            args = [str(self.paths[0]), str(self.fx.clips_dir),
                    *map(str, self.paths[1:]), str(Path(td)/'cards')]
            self.assertEqual(main(args), 0)
            with self.assertRaises(ValueError): main(args)


if __name__ == '__main__':
    unittest.main()
