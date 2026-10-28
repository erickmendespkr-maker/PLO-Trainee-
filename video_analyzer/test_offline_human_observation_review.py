"""Synthetic tests for the offline human-supplied observation review record."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_human_observation_review as mod


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n',
                    encoding='utf-8')


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for synthetic test media')
class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.master = Path(cls.base.name) / 'master.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                        '-t', '2', '-c:v', 'mpeg4', '-q:v', '8', str(cls.master)],
                       capture_output=True, check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.recording = self.root / 'recording.mp4'
        shutil.copyfile(self.master, self.recording)
        self.clips = self.root / 'exported_batch'
        self.clips.mkdir()
        self.clip = self.clips / 'table1.mp4'
        shutil.copyfile(self.master, self.clip)
        self.source = self.root / 'session_review.json'
        self.manual = self.root / 'manual.json'
        self.output = self.root / 'reviewed.json'
        self.html = self.root / 'reviewed.html'
        self.row = {
            'table_id': 1, 'hand_id': 'hand-1', 'decision_id': 'd1',
            'game_type': 'PLO5', 'clip_file': 'table1.mp4',
            'clip_sha256': mod.sha256(self.clip),
            'candidate_window_seconds': [0.25, 1.75],
            'clip_window_seconds': [0.0, 2.0],
            'action_pts_seconds': 1.0, 'observed_action': 'call',
            'review_label': 'overlapping_intervals_manual_review',
            'human_review_status': 'pending', 'model_conditional_only': True,
            'decision_quality_verified': False,
        }
        self.session = {
            'schema_version': 1,
            'analysis_status': 'offline_read_only_human_review_packet',
            'source_recording_sha256': mod.sha256(self.recording),
            'human_review_recorded': False,
            'video_evidence_independently_verified': False,
            'range_assumptions_verified': False,
            'decision_quality_verified': False,
            'automatic_clip_selection_authorized': False,
            'action_recommendation_authorized': False,
            'clip_media_hashes_rechecked': True, 'ffprobe_media_checked': True,
            'decision_count': 1, 'clip_count': 1, 'decisions': [self.row],
        }
        self.entry = {
            'table_id': 1, 'hand_id': 'hand-1', 'decision_id': 'd1',
            'outcome': 'confirmed', 'corrected_observed_action': None,
            'corrected_action_pts_seconds': None, 'note': 'Synthetic confirmation',
        }
        self.manual_data = {
            'schema_version': 1, 'source_session_review_sha256': '',
            'reviewer_alias': 'synthetic_reviewer', 'entries': [self.entry],
        }

    def run_build(self):
        save(self.source, self.session)
        self.manual_data['source_session_review_sha256'] = mod.sha256(self.source)
        save(self.manual, self.manual_data)
        return mod.build(self.recording, self.clips, self.source, self.manual,
                         self.output, self.html)

    def reject(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.run_build()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.html.exists())

    def test_confirmed_record(self):
        result = self.run_build()
        self.assertEqual(result['reviewed_decision_count'], 1)
        self.assertEqual(result['pending_decision_count'], 0)
        self.assertFalse(result['reviewer_identity_authenticated'])
        self.assertFalse(result['equity_ev_recomputed'])
        self.assertFalse(result['decision_quality_verified'])
        self.assertEqual(json.loads(self.output.read_text()), result)
        self.assertIn('src="exported_batch/table1.mp4"', self.html.read_text())
        self.assertNotIn('<script', self.html.read_text())

    def test_correct_action(self):
        self.entry.update(outcome='corrected', corrected_observed_action='raise',
                          corrected_action_pts_seconds=1.0,
                          note='Synthetic OCR correction')
        result = self.run_build()
        self.assertEqual(result['decisions'][0]['original_observed_action'], 'call')
        self.assertEqual(result['decisions'][0]['review']['corrected_observed_action'], 'raise')
        self.assertFalse(result['equity_ev_recomputed'])

    def test_correct_timestamp(self):
        self.entry.update(outcome='corrected', corrected_observed_action='call',
                          corrected_action_pts_seconds=1.5,
                          note='Synthetic timestamp correction')
        self.assertEqual(self.run_build()['decisions'][0]['review']
                         ['corrected_action_pts_seconds'], 1.5)

    def test_inconclusive(self):
        self.entry.update(outcome='inconclusive', note='Synthetic frame is unreadable')
        self.assertEqual(self.run_build()['decisions'][0]['review']['outcome'],
                         'inconclusive')

    def test_four_tables_partial_review(self):
        for i in range(2, 5):
            row = copy.deepcopy(self.row)
            row.update(table_id=i, hand_id=f'hand-{i}', decision_id=f'd{i}',
                       game_type='PLO6' if i % 2 == 0 else 'PLO5',
                       clip_file=f'table{i}.mp4')
            shutil.copyfile(self.master, self.clips / row['clip_file'])
            self.session['decisions'].append(row)
        self.session['decision_count'] = self.session['clip_count'] = 4
        result = self.run_build()
        self.assertEqual(result['pending_decision_count'], 3)
        self.assertEqual(result['clip_count'], 4)
        self.assertEqual(self.html.read_text().count('<video'), 4)

    def test_multiple_decisions_same_clip(self):
        row = copy.deepcopy(self.row)
        row.update(decision_id='d2', action_pts_seconds=1.5)
        self.session['decisions'].append(row)
        self.session['decision_count'] = 2
        result = self.run_build()
        self.assertEqual(result['pending_decision_count'], 1)
        self.assertEqual(result['clip_count'], 1)

    def test_duplicate_manual_decision(self):
        self.manual_data['entries'].append(copy.deepcopy(self.entry))
        self.reject()

    def test_unknown_manual_decision(self):
        self.entry['decision_id'] = 'other'
        self.reject()

    def test_bad_source_binding(self):
        self.manual_data['source_session_review_sha256'] = '0' * 64
        save(self.source, self.session)
        save(self.manual, self.manual_data)
        with self.assertRaises(ValueError):
            mod.build(self.recording, self.clips, self.source, self.manual,
                      self.output, self.html)

    def test_bad_recording_hash(self):
        self.session['source_recording_sha256'] = 'a' * 64
        self.reject()

    def test_bad_clip_hash(self):
        self.row['clip_sha256'] = 'a' * 64
        self.reject()

    def test_symlink_clip(self):
        self.clip.unlink()
        self.clip.symlink_to(self.master)
        self.reject()

    def test_symlink_recording(self):
        self.recording.unlink()
        self.recording.symlink_to(self.master)
        self.reject()

    def test_bad_clip_name(self):
        self.row['clip_file'] = '../escape.mp4'
        self.reject()

    def test_promoted_source(self):
        self.session['decision_quality_verified'] = True
        self.reject()

    def test_promoted_decision(self):
        self.row['decision_quality_verified'] = True
        self.reject()

    def test_previously_reviewed_source(self):
        self.row['human_review_status'] = 'confirmed'
        self.reject()

    def test_duplicate_source_decision(self):
        self.session['decisions'].append(copy.deepcopy(self.row))
        self.session['decision_count'] = 2
        self.reject()

    def test_invalid_source_timestamp(self):
        self.row['action_pts_seconds'] = 1.9
        self.reject()

    def test_invalid_correction_outside_hand(self):
        self.entry.update(outcome='corrected', corrected_observed_action='raise',
                          corrected_action_pts_seconds=1.9,
                          note='Synthetic bad correction')
        self.reject()

    def test_invalid_correction_nan(self):
        self.entry.update(outcome='corrected', corrected_observed_action='raise',
                          corrected_action_pts_seconds=float('nan'),
                          note='Synthetic invalid timestamp')
        with self.assertRaises(ValueError):
            self.run_build()

    def test_corrected_without_difference(self):
        self.entry.update(outcome='corrected', corrected_observed_action='call',
                          corrected_action_pts_seconds=1.0,
                          note='Synthetic unchanged correction')
        self.reject()

    def test_corrected_missing_explanation(self):
        self.entry.update(outcome='corrected', corrected_observed_action='raise',
                          corrected_action_pts_seconds=1.0, note='short')
        self.reject()

    def test_inconclusive_missing_explanation(self):
        self.entry.update(outcome='inconclusive', note='short')
        self.reject()

    def test_confirmed_cannot_correct(self):
        self.entry['corrected_observed_action'] = 'raise'
        self.reject()

    def test_inconclusive_cannot_correct(self):
        self.entry.update(outcome='inconclusive',
                          corrected_action_pts_seconds=1.0,
                          note='Synthetic inconclusive')
        self.reject()

    def test_bad_reviewer_alias(self):
        self.manual_data['reviewer_alias'] = '../../path'
        self.reject()

    def test_empty_reviews(self):
        self.manual_data['entries'] = []
        self.reject()

    def test_unexpected_annotation_field(self):
        self.entry['decision_quality_verified'] = True
        self.reject()

    def test_html_injection_escaped(self):
        self.entry['note'] = '<script>alert("bad")</script>'
        self.row['hand_id'] = self.entry['hand_id'] = '<img src=x onerror=alert(1)>'
        self.run_build()
        html = self.html.read_text()
        self.assertNotIn('<script>alert', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;', html)

    def test_output_not_overwritten(self):
        self.output.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_build()
        self.assertEqual(self.output.read_text(), 'KEEP')

    def test_html_not_overwritten(self):
        self.html.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_build()
        self.assertEqual(self.html.read_text(), 'KEEP')
        self.assertFalse(self.output.exists())

    def test_output_inside_clips(self):
        save(self.source, self.session)
        save(self.manual, self.manual_data)
        with self.assertRaises(ValueError):
            mod.build(self.recording, self.clips, self.source, self.manual,
                      self.clips / 'new.json', self.html)

    def test_duplicate_json_keys(self):
        save(self.source, self.session)
        self.manual.write_text('{"x":1,"x":2}', encoding='utf-8')
        with self.assertRaises(ValueError):
            mod.build(self.recording, self.clips, self.source, self.manual,
                      self.output, self.html)

    def test_nan_json(self):
        save(self.source, self.session)
        self.manual.write_text('{"x": NaN}', encoding='utf-8')
        with self.assertRaises(ValueError):
            mod.build(self.recording, self.clips, self.source, self.manual,
                      self.output, self.html)

    def test_source_modified_not_accepted(self):
        self.session['decision_count'] = 2
        self.reject()

    def test_bad_outcome(self):
        self.entry['outcome'] = 'proven_mistake'
        self.reject()

    def test_no_source_mutation(self):
        save(self.source, self.session)
        before = mod.sha256(self.source)
        self.run_build()
        self.assertEqual(before, mod.sha256(self.source))
        self.assertEqual(mod.sha256(self.recording),
                         self.session['source_recording_sha256'])

    def test_cli(self):
        save(self.source, self.session)
        self.manual_data['source_session_review_sha256'] = mod.sha256(self.source)
        save(self.manual, self.manual_data)
        self.assertEqual(mod.main([str(self.recording), str(self.clips),
                                   str(self.source), str(self.manual),
                                   str(self.output), str(self.html)]), 0)
        self.assertTrue(self.output.exists())


if __name__ == '__main__':
    unittest.main()