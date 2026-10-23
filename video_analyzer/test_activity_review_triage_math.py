"""Synthetic FFmpeg-backed tests for non-authorizing review triage."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from activity_hypothetical_math import build_hypothetical_report, digest
from activity_review_triage_math import STATUS, build_review_triage, main
from test_activity_math_clip_context import MathClipContextTests


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class ReviewTriageMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MathClipContextTests.setUpClass()
        cls.fx = MathClipContextTests

    @classmethod
    def tearDownClass(cls):
        cls.fx.tearDownClass()

    def build(self, **kwargs):
        fx = self.fx
        return build_review_triage(kwargs.get('manifest', fx.manifest),
                                   kwargs.get('clips_dir', fx.clips_dir),
                                   kwargs.get('worksheet', fx.worksheet),
                                   kwargs.get('request', fx.request),
                                   kwargs.get('report', fx.report))

    def test_four_candidates_no_auto_selection(self):
        output = self.build()
        self.assertEqual(output['analysis_status'], STATUS)
        self.assertEqual(len(output['candidates']), 4)
        self.assertFalse(output['auto_clip_selection_authorized'])
        self.assertFalse(output['authorized_for_ev_based_ranking'])
        self.assertTrue(all(not c['strategic_error_established'] for c in output['candidates']))

    def test_missing_fields_not_promoted(self):
        output = self.build()
        self.assertEqual(sum(c['review_category'] == 'needs_evidence'
                             for c in output['candidates']), 3)
        self.assertTrue(all(c['call_to_pot_ratio'] is None
                            for c in output['candidates'] if c['missing_fields']))

    def test_reviewed_call_exposure_is_heuristic_not_ev(self):
        first = next(c for c in self.build()['candidates'] if c['has_conditional_what_if'])
        self.assertEqual(first['call_to_pot_ratio'], .25)
        self.assertEqual(first['review_category'], 'human_attention_suggested')
        self.assertEqual(first['visual_evidence_confidence'], 'unverified')
        self.assertFalse(first['ev_ranking_authorized'])

    def test_deterministic(self):
        self.assertEqual(self.build(), self.build())

    def test_math_tamper_rejected(self):
        report = copy.deepcopy(self.fx.report)
        report['results'][0]['equity'] = .123
        with self.assertRaises(ValueError): self.build(report=report)

    def test_manifest_tamper_rejected(self):
        manifest = copy.deepcopy(self.fx.manifest)
        manifest['recording_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.build(manifest=manifest)

    def test_mp4_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            for item in self.fx.manifest['clips']:
                shutil.copy2(self.fx.clips_dir / item['filename'], Path(td) / item['filename'])
            file = Path(td) / self.fx.manifest['clips'][0]['filename']
            file.write_bytes(file.read_bytes() + b'tamper')
            with self.assertRaises(ValueError): self.build(clips_dir=Path(td))

    def test_plo6_still_unverified(self):
        worksheet = copy.deepcopy(self.fx.worksheet)
        worksheet['scenarios'][0]['reviewed_visible_inputs']['hero_cards'] = [
            'As','Ks','2d','3c','4h','5s']
        request = copy.deepcopy(self.fx.request)
        request['worksheet_sha256'] = digest(worksheet)
        request['scenarios'][0]['opponent_range'] = [{
            'cards': ['2c','3d','4c','5d','6h','7h'], 'weight': 1}]
        report = build_hypothetical_report(worksheet, request)
        result = self.build(worksheet=worksheet, request=request, report=report)
        self.assertFalse(result['authorized_for_ev_based_ranking'])

    def test_cli_new_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = []
            for name, obj in [('manifest', self.fx.manifest), ('worksheet', self.fx.worksheet),
                              ('request', self.fx.request), ('report', self.fx.report)]:
                path = root / f'{name}.json'
                path.write_text(json.dumps(obj), encoding='utf-8')
                paths.append(path)
            args = [str(paths[0]), str(self.fx.clips_dir), str(paths[1]),
                    str(paths[2]), str(paths[3]), str(root/'triage.json')]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(Path(args[-1]).read_text())['analysis_status'], STATUS)
            with self.assertRaises(ValueError): main(args)

    def test_cli_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'input.json'
            target.write_text('{}', encoding='utf-8')
            link = root / 'link.json'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                main([str(link), str(self.fx.clips_dir), str(target),
                      str(target), str(target), str(root/'out.json')])


if __name__ == '__main__':
    unittest.main()
