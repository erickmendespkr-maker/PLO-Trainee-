"""Real FFmpeg integration: prior priority module -> offline review dashboard."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_reviewed_ev_review_priority as prior
import offline_session_review_dashboard as dashboard


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class IntegrationTests(unittest.TestCase):
    def test_prior_priority_to_four_table_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / 'recording.mp4'
            batch = root / 'exported_batch'
            batch.mkdir()
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=10',
                            '-t', '2', '-c:v', 'mpeg4', '-q:v', '8', str(recording)],
                           check=True, capture_output=True, timeout=30)
            clips = []
            for table in range(1, 5):
                x = 320 * ((table - 1) % 2)
                y = 180 * ((table - 1) // 2)
                name = f'table{table}.mp4'
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                                '-i', str(recording), '-vf', f'crop=320:180:{x}:{y}',
                                '-c:v', 'mpeg4', '-q:v', '8', str(batch / name)],
                               check=True, capture_output=True, timeout=30)
                d = {'decision_id': f'd{table}', 'observed_action_label': 'call',
                     'action_pts_seconds': 1.0, 'model_conditional_only': True,
                     'action_recommendation_authorized': False,
                     'decision_quality_verified': False,
                     'source_reviewed_decision_ev_link_sha256': 'a'*64,
                     'source_ev_report_sha256': 'b'*64,
                     'source_ev_scenario_sha256': 'c'*64,
                     'call_range_assumption': 'synthetic call range',
                     'raise_called_range_assumption': 'synthetic raise range',
                     'fold_probability_hypothesis': '0.25',
                     'reviewed_pot_units': '100',
                     'ev_fold_hypothetical': '0',
                     'ev_call_hypothetical': '25',
                     'ev_raise_hypothetical': '50',
                     'ev_call_sampling_bounds': ['20', '30'],
                     'ev_raise_sampling_and_fold_assumption_bounds': ['40', '60']}
                clips.append({'table_id': table, 'hand_id': f'hand{table}',
                              'game_type_human_declared': 'PLO5' if table % 2 else 'PLO6',
                              'decision_quality_verified': False,
                              'clip_file': name, 'clip_sha256': prior.digest(batch / name),
                              'candidate_window_seconds': [0.25, 1.75],
                              'clip_window_seconds': [0.0, 2.0],
                              'decision_count': 1, 'hypothetical_ev_decisions': [d]})
            attachment = root / 'attachment.json'
            attachment.write_text(json.dumps({
                'schema_version': 1,
                'analysis_status': 'offline_reviewed_clip_hypothetical_ev_attachment_only',
                'source_recording_sha256': prior.digest(recording),
                'recording_and_exported_clip_hashes_checked': True,
                'video_evidence_independently_verified': False,
                'range_assumptions_verified': False,
                'ev_is_conditional_not_decision_quality': True,
                'automatic_clip_selection_authorized': False,
                'action_recommendation_authorized': False,
                'source_clip_hand_links_sha256': 'd'*64,
                'source_batch_report_sha256': 'e'*64,
                'source_hand_candidates_sha256': 'f'*64,
                'clip_count': 4, 'decision_count': 4, 'clips': clips}, indent=2))
            priority = root / 'priority.json'
            prior.rank(recording, batch, attachment, priority)
            manifest = dashboard.build(recording, batch, priority,
                                       root / 'review.json', root / 'review.html')
            self.assertEqual(manifest['clip_count'], 4)
            self.assertEqual(manifest['decision_count'], 4)
            self.assertEqual({r['game_type'] for r in manifest['decisions']}, {'PLO5', 'PLO6'})
            self.assertEqual((root / 'review.html').read_text().count('<video'), 4)
            self.assertTrue(all(r['media']['width'] == 320 for r in manifest['decisions']))
            self.assertFalse(manifest['action_recommendation_authorized'])


if __name__ == '__main__':
    unittest.main()
