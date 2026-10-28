"""Synthetic regression and fail-closed tests for manual EV review queue."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_reviewed_ev_review_priority as mod


def save(path, value):
    path.write_text(json.dumps(value, allow_nan=False) + '\n', encoding='utf-8')


class ReviewPriorityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.video = self.root / 'recording.mp4'
        self.video.write_bytes(b'synthetic local recording')
        self.batch = self.root / 'batch'
        self.batch.mkdir()
        self.clip = self.batch / 'table1.mp4'
        self.clip.write_bytes(b'synthetic clip bytes')
        self.report_file = self.root / 'attachment.json'
        self.output = self.root / 'priority.json'
        self.d = {'decision_id': 'd1', 'observed_action_label': 'call',
                  'action_pts_seconds': 5.0, 'model_conditional_only': True,
                  'action_recommendation_authorized': False,
                  'decision_quality_verified': False,
                  'source_reviewed_decision_ev_link_sha256': 'a'*64,
                  'source_ev_report_sha256': 'b'*64,
                  'source_ev_scenario_sha256': 'c'*64,
                  'call_range_assumption': 'hypothetical exact hand',
                  'raise_called_range_assumption': 'hypothetical exact hand',
                  'fold_probability_hypothesis': '0.25',
                  'reviewed_pot_units': '100',
                  'ev_fold_hypothetical': '0.00',
                  'ev_call_hypothetical': '25.00',
                  'ev_raise_hypothetical': '50.00',
                  'ev_call_sampling_bounds': ['20.00', '30.00'],
                  'ev_raise_sampling_and_fold_assumption_bounds': ['40.00', '60.00']}
        self.c = {'table_id': 1, 'hand_id': 'h1', 'game_type_human_declared': 'PLO5',
                  'decision_quality_verified': False,
                  'clip_file': self.clip.name, 'clip_sha256': mod.digest(self.clip),
                  'candidate_window_seconds': [1.0, 8.0],
                  'clip_window_seconds': [0.0, 9.0],
                  'decision_count': 1, 'hypothetical_ev_decisions': [self.d]}
        self.r = {'schema_version': 1,
                  'analysis_status': 'offline_reviewed_clip_hypothetical_ev_attachment_only',
                  'source_recording_sha256': mod.digest(self.video),
                  'recording_and_exported_clip_hashes_checked': True,
                  'video_evidence_independently_verified': False,
                  'range_assumptions_verified': False,
                  'ev_is_conditional_not_decision_quality': True,
                  'automatic_clip_selection_authorized': False,
                  'action_recommendation_authorized': False,
                  'source_clip_hand_links_sha256': 'd'*64,
                  'source_batch_report_sha256': 'e'*64,
                  'source_hand_candidates_sha256': 'f'*64,
                  'clip_count': 1, 'decision_count': 1, 'clips': [self.c]}
        self.sync()

    def sync(self):
        save(self.report_file, self.r)

    def run_rank(self, **kwargs):
        self.sync()
        return mod.rank(self.video, self.batch, self.report_file, self.output, **kwargs)

    def reject(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.run_rank()
        self.assertFalse(self.output.exists())

    def test_separated_conditional_intervals(self):
        out = self.run_rank()
        q = out['manual_review_queue'][0]
        self.assertEqual(q['review_label'], 'model_interval_separated_manual_review')
        self.assertEqual(q['positive_interval_separation_units'], '10.00')
        self.assertEqual(q['possible_gap_upper_units'], '40.00')
        self.assertFalse(out['automatic_clip_selection_authorized'])
        self.assertFalse(q['decision_quality_verified'])
        self.assertIn('nao foi comprovado erro', q['review_explanation'])
        self.assertEqual(q['call_range_assumption'], 'hypothetical exact hand')
        self.assertEqual(json.loads(self.output.read_text()), out)

    def test_overlapping_intervals(self):
        self.d['ev_raise_sampling_and_fold_assumption_bounds'] = ['24.00', '60.00']
        q = self.run_rank()['manual_review_queue'][0]
        self.assertEqual(q['review_label'], 'overlapping_intervals_manual_review')
        self.assertEqual(q['positive_interval_separation_units'], '0')

    def test_no_positive_gap(self):
        self.d['observed_action_label'] = 'raise'
        self.d['ev_raise_sampling_and_fold_assumption_bounds'] = ['40.00', '60.00']
        self.assertEqual(self.run_rank()['manual_review_queue'][0]['review_label'],
                         'no_positive_model_gap_detected')

    def test_fold_observed(self):
        self.d['observed_action_label'] = 'fold'
        self.assertEqual(self.run_rank()['manual_review_queue'][0]['positive_interval_separation_units'], '40.00')

    def test_raise_observed(self):
        self.d['observed_action_label'] = 'raise'
        self.assertEqual(self.run_rank()['manual_review_queue'][0]['observed_ev_interval_units'],
                         ['40.00', '60.00'])

    def test_threshold_suppresses_separation(self):
        self.assertEqual(self.run_rank(min_separation='10.00')['manual_review_queue'][0]['review_label'],
                         'overlapping_intervals_manual_review')

    def test_negative_threshold(self):
        with self.assertRaises(ValueError): self.run_rank(min_separation='-1')

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError): self.run_rank(min_separation='NaN')

    def test_two_decisions_ordered(self):
        d2 = copy.deepcopy(self.d)
        d2.update(decision_id='d2', action_pts_seconds=3.0,
                  observed_action_label='raise')
        self.c['hypothetical_ev_decisions'].append(d2)
        self.c['decision_count'] = self.r['decision_count'] = 2
        rows = self.run_rank()['manual_review_queue']
        self.assertEqual([x['decision_id'] for x in rows], ['d1', 'd2'])

    def test_four_tables(self):
        for table in range(2, 5):
            c = copy.deepcopy(self.c)
            c.update(table_id=table, hand_id=f'h{table}', clip_file=f'table{table}.mp4')
            path = self.batch / c['clip_file']
            path.write_bytes(f'synthetic table {table}'.encode())
            c['clip_sha256'] = mod.digest(path)
            c['hypothetical_ev_decisions'][0]['decision_id'] = f'd{table}'
            self.r['clips'].append(c)
        self.r['clip_count'] = self.r['decision_count'] = 4
        self.assertEqual(self.run_rank()['decision_count'], 4)

    def test_duplicate_decision(self):
        self.c['hypothetical_ev_decisions'].append(copy.deepcopy(self.d))
        self.c['decision_count'] = self.r['decision_count'] = 2
        self.reject()

    def test_duplicate_clip(self):
        self.r['clips'].append(copy.deepcopy(self.c))
        self.r['clip_count'] = 2
        self.r['decision_count'] = 2
        self.reject()

    def test_same_mp4_reused_for_two_hands(self):
        second = copy.deepcopy(self.c)
        second['hand_id'] = 'h2'
        second['hypothetical_ev_decisions'][0]['decision_id'] = 'd2'
        self.r['clips'].append(second)
        self.r['clip_count'] = self.r['decision_count'] = 2
        self.reject()

    def test_tampered_clip(self):
        self.clip.write_bytes(b'tampered')
        self.reject()

    def test_tampered_recording(self):
        self.video.write_bytes(b'tampered')
        self.reject()

    def test_promoted_auto_selection(self):
        self.r['automatic_clip_selection_authorized'] = True
        self.reject()

    def test_promoted_decision_quality(self):
        self.d['decision_quality_verified'] = True
        self.reject()

    def test_promoted_range_verification(self):
        self.r['range_assumptions_verified'] = True
        self.reject()

    def test_missing_hypothesis(self):
        self.d['call_range_assumption'] = '  '
        self.reject()

    def test_boolean_timestamp(self):
        self.d['action_pts_seconds'] = True
        self.reject()

    def test_outside_hand_timestamp(self):
        self.d['action_pts_seconds'] = 8.5
        self.reject()

    def test_invalid_interval_order(self):
        self.d['ev_call_sampling_bounds'] = ['30.00', '20.00']
        self.reject()

    def test_estimate_outside_interval(self):
        self.d['ev_call_hypothetical'] = '99.00'
        self.reject()

    def test_invalid_fold_baseline(self):
        self.d['ev_fold_hypothetical'] = '1.00'
        self.reject()

    def test_nan_probability(self):
        self.d['fold_probability_hypothesis'] = 'NaN'
        self.reject()

    def test_wrong_decision_count(self):
        self.r['decision_count'] = 2
        self.reject()

    def test_existing_output_not_overwritten(self):
        self.output.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_rank()
        self.assertEqual(self.output.read_text(), 'KEEP')

    def test_output_inside_batch(self):
        self.sync()
        with self.assertRaises(ValueError):
            mod.rank(self.video, self.batch, self.report_file, self.batch / 'report.json')

    def test_symlink_clip(self):
        self.clip.rename(self.root / 'real.mp4')
        self.clip.symlink_to(self.root / 'real.mp4')
        self.reject()

    def test_unsafe_clip_path(self):
        self.c['clip_file'] = '../table1.mp4'
        self.reject()

    def test_empty_decisions(self):
        self.c['decision_count'] = self.r['decision_count'] = 0
        self.c['hypothetical_ev_decisions'] = []
        self.reject()

    def test_duplicate_json_keys(self):
        self.sync()
        self.report_file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            mod.rank(self.video, self.batch, self.report_file, self.output)

    def test_nan_json(self):
        self.sync()
        self.report_file.write_text('{"value":NaN}')
        with self.assertRaises(ValueError):
            mod.rank(self.video, self.batch, self.report_file, self.output)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
    def test_real_ffmpeg_mp4_hash_verification(self):
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                        '-t', '2', '-c:v', 'mpeg4', '-q:v', '8', str(self.video)],
                       check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(self.video), '-t', '1', '-c:v', 'mpeg4',
                        '-q:v', '8', str(self.clip)], check=True, capture_output=True)
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                'stream=width,height', '-of', 'json', str(self.clip)],
                               check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(probe.stdout)['streams'][0]['width'], 320)
        self.r['source_recording_sha256'] = mod.digest(self.video)
        self.c['clip_sha256'] = mod.digest(self.clip)
        self.assertEqual(self.run_rank()['decision_count'], 1)


if __name__ == '__main__':
    unittest.main()
