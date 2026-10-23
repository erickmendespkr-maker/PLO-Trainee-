"""Synthetic FFmpeg-backed checks for conditional math explanation sidecars."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from activity_hypothetical_math import build_hypothetical_report, digest
from activity_math_explanation import STATUS, build_explanations, main
from test_activity_math_clip_context import MathClipContextTests


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class MathExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MathClipContextTests.setUpClass()
        cls.fx = MathClipContextTests

    @classmethod
    def tearDownClass(cls):
        cls.fx.tearDownClass()

    def build(self, **overrides):
        fx = self.fx
        return build_explanations(overrides.get('manifest', fx.manifest),
                                  overrides.get('clips_dir', fx.clips_dir),
                                  overrides.get('worksheet', fx.worksheet),
                                  overrides.get('request', fx.request),
                                  overrides.get('report', fx.report))

    def test_four_clips_one_what_if_and_three_without_math(self):
        output = self.build()
        self.assertEqual(output['analysis_status'], STATUS)
        self.assertEqual(len(output['clips']), 4)
        self.assertEqual(sum(c['conditional_result'] is not None for c in output['clips']), 1)
        self.assertTrue(all(c['strategic_error_established'] is False for c in output['clips']))
        self.assertFalse(output['authorized_for_ev_based_ranking'])
        self.assertIn('Sem cálculo', output['clips'][1]['display_card_lines'][3])

    def test_math_values_and_explicit_assumptions(self):
        first = self.build()['clips'][0]
        self.assertEqual(first['conditional_result']['variant'], 'PLO5')
        self.assertEqual(first['conditional_result']['equity'], 1)
        self.assertEqual(first['conditional_result']['call_ev_vs_fold'], 100)
        self.assertEqual(first['hypotheses']['range_combinations'], 1)
        self.assertEqual(first['hypotheses']['seed'], 17)
        self.assertFalse(first['hypotheses']['future_betting_included'])
        self.assertIn('NÃO é EV real', first['display_card_lines'][-1])
        self.assertEqual(first['observed_review']['status'],
                         'human_attested_not_independently_video_verified')

    def test_deterministic_output_and_source_hash(self):
        self.assertEqual(self.build(), self.build())
        self.assertEqual(self.build()['source_math_report_sha256'], digest(self.fx.report))

    def test_plo6_supported_but_not_authorized(self):
        worksheet = copy.deepcopy(self.fx.worksheet)
        worksheet['scenarios'][0]['reviewed_visible_inputs']['hero_cards'] = [
            'As','Ks','2d','3c','4h','5s']
        request = copy.deepcopy(self.fx.request)
        request['worksheet_sha256'] = digest(worksheet)
        request['scenarios'][0]['opponent_range'] = [{
            'cards': ['2c','3d','4c','5d','6h','7h'], 'weight': 1}]
        report = build_hypothetical_report(worksheet, request)
        first = self.build(worksheet=worksheet, request=request, report=report)['clips'][0]
        self.assertEqual(first['conditional_result']['variant'], 'PLO6')
        self.assertFalse(first['eligible_for_ev_ranking'])

    def test_tampered_math_rejected(self):
        report = copy.deepcopy(self.fx.report)
        report['results'][0]['equity'] = .123
        with self.assertRaises(ValueError): self.build(report=report)

    def test_wrong_recording_identity_rejected(self):
        worksheet = copy.deepcopy(self.fx.worksheet)
        worksheet['recording_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.build(worksheet=worksheet)

    def test_modified_clip_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            for c in self.fx.manifest['clips']:
                shutil.copy2(self.fx.clips_dir / c['filename'], Path(td) / c['filename'])
            path = Path(td) / self.fx.manifest['clips'][0]['filename']
            path.write_bytes(path.read_bytes() + b'altered')
            with self.assertRaises(ValueError): self.build(clips_dir=Path(td))

    def test_wrong_action_rejected(self):
        worksheet = copy.deepcopy(self.fx.worksheet)
        worksheet['scenarios'][0]['reviewed_visible_inputs']['observed_action'] = 'raise'
        with self.assertRaises(ValueError): self.build(worksheet=worksheet)

    def test_cli_writes_new_file_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = []
            for name, value in [('manifest', self.fx.manifest), ('worksheet', self.fx.worksheet),
                                ('request', self.fx.request), ('report', self.fx.report)]:
                p = root / f'{name}.json'
                p.write_text(json.dumps(value), encoding='utf-8')
                paths.append(p)
            args = [str(paths[0]), str(self.fx.clips_dir), str(paths[1]),
                    str(paths[2]), str(paths[3]), str(root/'explanation.json')]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(Path(args[-1]).read_text())['analysis_status'], STATUS)
            with self.assertRaises(ValueError): main(args)

    def test_cli_rejects_symlinked_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'manifest.json'
            target.write_text(json.dumps(self.fx.manifest), encoding='utf-8')
            link = root / 'link.json'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                main([str(link), str(self.fx.clips_dir), str(target),
                      str(target), str(target), str(root/'out.json')])


if __name__ == '__main__':
    unittest.main()
