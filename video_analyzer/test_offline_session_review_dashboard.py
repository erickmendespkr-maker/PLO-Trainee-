"""Offline synthetic and FFmpeg/FFprobe tests; no poker account or real session."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_session_review_dashboard as mod


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and FFprobe required')
class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.master = Path(cls.base.name) / 'source.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                        '-t', '2', '-c:v', 'mpeg4', '-q:v', '8', str(cls.master)],
                       check=True, capture_output=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.video = self.root / 'recording.mp4'
        shutil.copyfile(self.master, self.video)
        self.batch = self.root / 'exported_batch'
        self.batch.mkdir()
        self.clip = self.batch / 'table1.mp4'
        shutil.copyfile(self.master, self.clip)
        self.source = self.root / 'priority.json'
        self.json = self.root / 'review.json'
        self.html = self.root / 'review.html'
        self.row = {
            'table_id': 1, 'hand_id': 'hand-1', 'game_type': 'PLO5',
            'clip_file': 'table1.mp4', 'clip_sha256': mod.digest(self.clip),
            'clip_window_seconds': [0.0, 2.0],
            'candidate_window_seconds': [0.25, 1.75],
            'decision_id': 'd1', 'action_pts_seconds': 1.0,
            'observed_action': 'call',
            'review_label': 'model_interval_separated_manual_review',
            'positive_interval_separation_units': '10',
            'possible_gap_upper_units': '40',
            'observed_ev_interval_units': ['20', '30'],
            'fold_probability_hypothesis': '0.25',
            'call_range_assumption': 'synthetic range A',
            'raise_called_range_assumption': 'synthetic range B',
            'source_ev_report_sha256': 'a'*64,
            'source_reviewed_decision_ev_link_sha256': 'b'*64,
            'range_hypotheses_not_verified': True,
            'model_sampling_bounds_not_total_uncertainty': True,
            'human_review_required': True,
            'decision_quality_verified': False,
            'automatic_clip_selection_authorized': False,
            'action_recommendation_authorized': False,
        }
        self.priority = {
            'schema_version': 1,
            'analysis_status': 'offline_hypothetical_ev_manual_review_priority_only',
            'source_recording_sha256': mod.digest(self.video),
            'source_ev_attachments_sha256': 'c'*64,
            'video_evidence_independently_verified': False,
            'range_assumptions_verified': False,
            'decision_quality_verified': False,
            'automatic_clip_selection_authorized': False,
            'action_recommendation_authorized': False,
            'clip_media_hashes_rechecked': True,
            'original_ev_sources_recomputed_in_this_step': False,
            'min_conditional_interval_separation_units': '0',
            'clip_count': 1, 'decision_count': 1,
            'manual_review_queue': [self.row],
        }

    def run_build(self):
        save(self.source, self.priority)
        return mod.build(self.video, self.batch, self.source, self.json, self.html)

    def reject(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.run_build()
        self.assertFalse(self.json.exists())
        self.assertFalse(self.html.exists())

    def test_successful_html_json_report(self):
        result = self.run_build()
        self.assertEqual(result['decision_count'], 1)
        self.assertEqual(result['clip_count'], 1)
        self.assertTrue(result['ffprobe_media_checked'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['human_review_recorded'])
        self.assertEqual(json.loads(self.json.read_text()), result)
        self.assertIn('src="exported_batch/table1.mp4"', self.html.read_text())
        self.assertIn('preload="none"', self.html.read_text())
        self.assertNotIn('<script', self.html.read_text())

    def test_four_tables(self):
        for i in range(2, 5):
            row = copy.deepcopy(self.row)
            row.update(table_id=i, hand_id=f'hand-{i}', decision_id=f'd{i}',
                       clip_file=f'table{i}.mp4')
            shutil.copyfile(self.master, self.batch / row['clip_file'])
            self.priority['manual_review_queue'].append(row)
        self.priority['decision_count'] = self.priority['clip_count'] = 4
        result = self.run_build()
        self.assertEqual(result['decision_count'], 4)
        self.assertEqual(result['clip_count'], 4)
        self.assertEqual(self.html.read_text().count('<video'), 4)

    def test_multiple_decisions_one_hand(self):
        row = copy.deepcopy(self.row)
        row['decision_id'] = 'd2'
        row['action_pts_seconds'] = 1.5
        self.priority['manual_review_queue'].append(row)
        self.priority['decision_count'] = 2
        self.assertEqual(self.run_build()['clip_count'], 1)

    def test_html_injection_escaped(self):
        self.row['hand_id'] = '<img src=x onerror=alert(1)>'
        self.row['call_range_assumption'] = '<script>alert(1)</script>'
        self.row['decision_id'] = '" autofocus'
        self.run_build()
        content = self.html.read_text()
        self.assertNotIn('<script>alert', content)
        self.assertNotIn('<img src=x', content)
        self.assertIn('&lt;script&gt;', content)

    def test_invalid_media_bytes(self):
        self.clip.write_bytes(b'not mp4')
        self.row['clip_sha256'] = mod.digest(self.clip)
        self.reject()

    def test_tampered_clip(self):
        self.clip.write_bytes(b'changed')
        self.reject()

    def test_tampered_recording(self):
        self.video.write_bytes(b'changed')
        self.reject()

    def test_unsafe_filename(self):
        self.row['clip_file'] = '../table1.mp4'
        self.reject()

    def test_symlink_clip(self):
        self.clip.unlink()
        self.clip.symlink_to(self.master)
        self.reject()

    def test_symlink_json(self):
        self.source.symlink_to(self.master)
        with self.assertRaises(ValueError):
            mod.build(self.video, self.batch, self.source, self.json, self.html)

    def test_duplicate_decision(self):
        self.priority['manual_review_queue'].append(copy.deepcopy(self.row))
        self.priority['decision_count'] = 2
        self.reject()

    def test_clip_assigned_to_other_hand(self):
        row = copy.deepcopy(self.row)
        row.update(hand_id='other', decision_id='d2')
        self.priority['manual_review_queue'].append(row)
        self.priority['decision_count'] = 2
        self.reject()

    def test_hand_assigned_to_other_clip(self):
        row = copy.deepcopy(self.row)
        row.update(decision_id='d2', clip_file='table2.mp4')
        shutil.copyfile(self.master, self.batch / 'table2.mp4')
        self.priority['manual_review_queue'].append(row)
        self.priority['decision_count'] = self.priority['clip_count'] = 2
        self.reject()

    def test_wrong_decision_count(self):
        self.priority['decision_count'] = 2
        self.reject()

    def test_wrong_clip_count(self):
        self.priority['clip_count'] = 2
        self.reject()

    def test_invalid_label(self):
        self.row['review_label'] = 'proven_mistake'
        self.reject()

    def test_label_bound_mismatch(self):
        self.row['review_label'] = 'overlapping_intervals_manual_review'
        self.reject()

    def test_overlapping_label_valid(self):
        self.row['positive_interval_separation_units'] = '0'
        self.row['review_label'] = 'overlapping_intervals_manual_review'
        self.assertEqual(self.run_build()['decisions'][0]['review_label'],
                         'overlapping_intervals_manual_review')

    def test_no_gap_valid(self):
        self.row['positive_interval_separation_units'] = '0'
        self.row['possible_gap_upper_units'] = '0'
        self.row['review_label'] = 'no_positive_model_gap_detected'
        self.assertEqual(self.run_build()['decisions'][0]['review_label'],
                         'no_positive_model_gap_detected')

    def test_negative_gap(self):
        self.row['positive_interval_separation_units'] = '-1'
        self.reject()

    def test_invalid_timestamp(self):
        self.row['action_pts_seconds'] = True
        self.reject()

    def test_outside_hand_timestamp(self):
        self.row['action_pts_seconds'] = 1.99
        self.reject()

    def test_bad_duration(self):
        self.row['clip_window_seconds'] = [0, 20]
        self.reject()

    def test_missing_range(self):
        self.row['call_range_assumption'] = '  '
        self.reject()

    def test_false_review_flags(self):
        self.priority['automatic_clip_selection_authorized'] = True
        self.reject()

    def test_promoted_decision_quality(self):
        self.row['decision_quality_verified'] = True
        self.reject()

    def test_nan_json(self):
        self.source.write_text('{"x": NaN}', encoding='utf-8')
        with self.assertRaises(ValueError):
            mod.build(self.video, self.batch, self.source, self.json, self.html)

    def test_duplicate_json_keys(self):
        self.source.write_text('{"x":1,"x":2}', encoding='utf-8')
        with self.assertRaises(ValueError):
            mod.build(self.video, self.batch, self.source, self.json, self.html)

    def test_existing_html_not_overwritten(self):
        self.html.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_build()
        self.assertEqual(self.html.read_text(), 'KEEP')
        self.assertFalse(self.json.exists())

    def test_existing_json_not_overwritten(self):
        self.json.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_build()
        self.assertEqual(self.json.read_text(), 'KEEP')
        self.assertFalse(self.html.exists())

    def test_output_inside_batch_rejected(self):
        save(self.source, self.priority)
        with self.assertRaises(ValueError):
            mod.build(self.video, self.batch, self.source,
                      self.batch / 'report.json', self.html)

    def test_cli(self):
        save(self.source, self.priority)
        self.assertEqual(mod.main([str(self.video), str(self.batch), str(self.source),
                                   str(self.json), str(self.html)]), 0)
        self.assertTrue(self.json.is_file())


if __name__ == '__main__':
    unittest.main()
