"""Synthetic, offline tests for explicit human-selected hypothetical math clips."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from hand_math_clip_export import export, plan, template, _caption
from hand_math_scenario_run import run
from video_segments import probe_video
from test_hand_math_scenario_run import HypotheticalMathTests


class HandMathClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HypotheticalMathTests.setUpClass()
        cls.temp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.temp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=12:duration=5',
                        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-threads', '2', str(cls.video)], check=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.fixture = HypotheticalMathTests(methodName='test_empty_all_four_tables_skipped')
        self.fixture.setUp()
        self.intake = copy.deepcopy(self.fixture.intake)
        self.intake['recording_sha256'] = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.filled = copy.deepcopy(self.intake)
        self.filled['tasks'][0]['manual_scenario_draft'] = copy.deepcopy(self.fixture.fill())
        self.intake_raw = json.dumps(self.intake).encode()
        self.filled_raw = json.dumps(self.filled).encode()
        self.math = run(self.intake, self.filled, hashlib.sha256(self.intake_raw).hexdigest())
        self.math_raw = json.dumps(self.math).encode()
        self.selection = template(self.video, self.intake, self.filled, self.math,
                                  self.intake_raw, self.filled_raw, self.math_raw)
        self.selection['regions_human_confirmed'] = True
        self.selection['regions'] = [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180},
            {'table_id': 2, 'x': 320, 'y': 0, 'width': 320, 'height': 180},
            {'table_id': 3, 'x': 0, 'y': 180, 'width': 320, 'height': 180},
            {'table_id': 4, 'x': 320, 'y': 180, 'width': 320, 'height': 180},
        ]
        self.selection['clips'][0]['reviewer_approved'] = True
        self.selection['clips'][0]['reviewer_note'] = 'Revisão manual sintética da decisão'

    def check(self, selection=None, intake=None, filled=None, result=None):
        return plan(self.video, self.intake if intake is None else intake,
                    self.filled if filled is None else filled,
                    self.math if result is None else result,
                    self.selection if selection is None else selection,
                    self.intake_raw, self.filled_raw, self.math_raw)

    def test_template_unapproved_by_default(self):
        s = template(self.video, self.intake, self.filled, self.math,
                     self.intake_raw, self.filled_raw, self.math_raw)
        self.assertFalse(s['regions_human_confirmed'])
        self.assertFalse(s['clips'][0]['reviewer_approved'])
        with self.assertRaises(ValueError): self.check(s)

    def test_selection_passes_without_auto_ranking(self):
        result = self.check()
        self.assertEqual(len(result['clips']), 1)
        self.assertEqual(result['clips'][0]['table_id'], 1)
        self.assertEqual(result['clips'][0]['timestamp'], 2.0)

    def test_math_recompute_detects_tampering(self):
        result = copy.deepcopy(self.math)
        result['results'][0]['equity'] = .1
        with self.assertRaisesRegex(ValueError, 'recomputation'):
            self.check(result=result)

    def test_recording_sha_pinned(self):
        edited = copy.deepcopy(self.intake)
        edited['recording_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'recording'):
            self.check(intake=edited)

    def test_selection_sha_pinned(self):
        s = copy.deepcopy(self.selection)
        s['source_math_sha256'] = 'f' * 64
        with self.assertRaises(ValueError): self.check(s)

    def test_missing_manual_approval_rejected(self):
        s = copy.deepcopy(self.selection)
        s['clips'][0]['reviewer_approved'] = False
        with self.assertRaises(ValueError): self.check(s)

    def test_no_unapproved_regions(self):
        s = copy.deepcopy(self.selection)
        s['regions_human_confirmed'] = False
        with self.assertRaises(ValueError): self.check(s)

    def test_invalid_cross_table_selection(self):
        s = copy.deepcopy(self.selection)
        s['clips'][0]['table_id'] = 2
        with self.assertRaises(ValueError): self.check(s)

    def test_reject_timestamp_tamper(self):
        s = copy.deepcopy(self.selection)
        s['clips'][0]['timestamp'] = 2.2
        with self.assertRaises(ValueError): self.check(s)

    def test_reject_invalid_clip_window(self):
        for start, end in ((3, 4), (0, 2), (2, 2.2), (0, 90)):
            s = copy.deepcopy(self.selection)
            s['clips'][0]['start'], s['clips'][0]['end'] = start, end
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.check(s)

    def test_reject_overlapping_regions(self):
        s = copy.deepcopy(self.selection)
        s['regions'][1]['x'] = 100
        with self.assertRaises(ValueError): self.check(s)

    def test_reject_unsafe_reviewer_note(self):
        for note in ('', 'hello\nworld', 'a' * 181, 'hello\u202eRTL'):
            s = copy.deepcopy(self.selection)
            s['clips'][0]['reviewer_note'] = note
            with self.subTest(note=note[:10]), self.assertRaises(ValueError):
                self.check(s)

    def test_reject_duplicate_selection(self):
        s = copy.deepcopy(self.selection)
        s['clips'].append(copy.deepcopy(s['clips'][0]))
        with self.assertRaises(ValueError): self.check(s)

    def test_reject_unverified_math_claims(self):
        result = copy.deepcopy(self.math)
        result['results'][0]['strategic_error_established'] = True
        with self.assertRaises(ValueError): self.check(result=result)

    def test_caption_contains_explicit_hypothetical_warning(self):
        caption = _caption(self.check()['clips'][0])
        self.assertIn('NÃO comprova erro', caption)
        self.assertIn('IC95', caption)
        self.assertIn('combinações hipotéticas', caption)

    def test_export_real_ffmpeg_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / name for name in ('intake.json', 'filled.json', 'math.json', 'selection.json')]
            for path, raw in zip(paths, (self.intake_raw, self.filled_raw, self.math_raw,
                                         json.dumps(self.selection).encode())):
                path.write_bytes(raw)
            out = Path(temp) / 'clips'
            manifest = export(self.video, *paths, out)
            self.assertEqual(manifest['clips_generated'], 1)
            self.assertFalse(manifest['strategic_error_established'])
            clip = out / manifest['clips'][0]['filename']
            self.assertEqual(hashlib.sha256(clip.read_bytes()).hexdigest(), manifest['clips'][0]['mp4_sha256'])
            info = probe_video(clip)
            self.assertEqual((info['width'], info['height']), (960, 540))
            self.assertGreater(info['duration'], 8)
            self.assertTrue((out / 'hand_math_clip_manifest.json').is_file())
            with self.assertRaises(ValueError): export(self.video, *paths, out)

    def test_two_tables_plo5_plo6_and_manual_order(self):
        fixture = HypotheticalMathTests(methodName='test_empty_all_four_tables_skipped')
        fixture.setUp()
        fixture.fill(0)
        fixture.fill(1, variant=6, action='raise')
        self.filled['tasks'][1]['manual_scenario_draft'] = copy.deepcopy(
            fixture.completed['tasks'][1]['manual_scenario_draft'])
        self.filled_raw = json.dumps(self.filled).encode()
        self.math = run(self.intake, self.filled, hashlib.sha256(self.intake_raw).hexdigest())
        self.math_raw = json.dumps(self.math).encode()
        self.selection = template(self.video, self.intake, self.filled, self.math,
                                  self.intake_raw, self.filled_raw, self.math_raw)
        self.selection['regions_human_confirmed'] = True
        self.selection['regions'] = [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180},
            {'table_id': 2, 'x': 320, 'y': 0, 'width': 320, 'height': 180},
        ]
        for item in self.selection['clips']:
            item['reviewer_approved'] = True
            item['reviewer_note'] = 'Selecionado manualmente para revisar hipóteses'
        self.assertEqual(len(self.check()['clips']), 2)
        self.assertIn('fold: 20.0%', _caption(self.check()['clips'][1]))
        self.assertIn('PLO6', _caption(self.check()['clips'][1]))

    def test_unfilled_or_blocked_task_cannot_be_exported(self):
        s = copy.deepcopy(self.selection)
        s['clips'][0]['entry_id'] = self.intake['tasks'][1]['entry_id']
        s['clips'][0]['table_id'] = 2
        with self.assertRaises(ValueError): self.check(s)

    def test_explicit_no_auto_ranking_claim(self):
        s = copy.deepcopy(self.selection)
        s['automatic_clip_selection_authorized'] = True
        with self.assertRaises(ValueError): self.check(s)

    def test_export_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / name for name in ('intake.json', 'filled.json', 'math.json', 'selection.json')]
            paths[0].write_text('{"a":1,"a":2}')
            for path, raw in zip(paths[1:], (self.filled_raw, self.math_raw, json.dumps(self.selection).encode())):
                path.write_bytes(raw)
            with self.assertRaises(ValueError): export(self.video, *paths, Path(temp) / 'out')

    def test_export_rejects_symlink_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / name for name in ('intake.json', 'filled.json', 'math.json', 'selection.json')]
            for path, raw in zip(paths, (self.intake_raw, self.filled_raw, self.math_raw,
                                         json.dumps(self.selection).encode())):
                path.write_bytes(raw)
            link = Path(temp) / 'link.json'
            link.symlink_to(paths[3])
            with self.assertRaises(ValueError): export(self.video, *paths[:3], link, Path(temp) / 'out')


if __name__ == '__main__':
    unittest.main()
