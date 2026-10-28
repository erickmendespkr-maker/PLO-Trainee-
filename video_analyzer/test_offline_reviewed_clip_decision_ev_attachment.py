"""Synthetic, fail-closed checks for offline clip + hypothetical EV attachments."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_reviewed_clip_decision_ev_attachment as mod


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return path


class ClipDecisionEVAttachmentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.video = self.root / 'recording.mp4'
        self.video.write_bytes(b'synthetic video marker, not a poker recording')
        self.directory = self.root / 'batch'
        self.directory.mkdir()
        self.links = self.root / 'links.json'
        self.decision = self.root / 'decision.json'
        self.output = self.root / 'attached.json'
        fixture = Path(__file__).parent / 'fixtures' / 'cycle161_reviewed_decision_ev.json'
        self.decision_data = json.loads(fixture.read_text(encoding='utf-8'))
        self.assertEqual(mod.digest(self.video), self.decision_data['recording_sha256'])
        self.make_batch([(1, 'hand1', 'PLO5')])
        write(self.decision, self.decision_data)

    def make_batch(self, entries):
        video_sha = mod.digest(self.video)
        self.batch_entries = []
        self.linked = []
        for n, (table, hand, game) in enumerate(entries, 1):
            name = f'{n:02d}_table{table}_{hand}.mp4'
            clip = self.directory / name
            if not clip.exists():
                clip.write_bytes(f'synthetic mp4 placeholder {n}'.encode())
            req = {'schema_version': 1, 'hand_id': hand, 'table_id': table,
                   'source_video_sha256': video_sha, 'reviewer_confirmed_offline': True,
                   'start_seconds': 0.0, 'end_seconds': 9.0,
                   'crop': {'x': 0, 'y': 0, 'width': 320, 'height': 180},
                   'explanation': 'Synthetic manual review, no real poker observations'}
            req_path = write(self.directory / f'{n:02d}_request.json', req)
            sidecar = {'analysis_status': 'manually_selected_offline_clip',
                       'source_video_sha256': video_sha,
                       'source_request_sha256': mod.digest(req_path),
                       'clip_sha256': mod.digest(clip), 'hand_id': hand, 'table_id': table,
                       'start_seconds': 0.0, 'end_seconds': 9.0,
                       'crop': req['crop'], 'explanation': req['explanation'],
                       'video_evidence_verified': False,
                       'automatic_clip_selection_authorized': False}
            write(self.directory / (name + '.json'), sidecar)
            self.batch_entries.append({'hand_id': hand, 'table_id': table,
                                       'clip_file': name, 'sidecar_file': name + '.json',
                                       'request_file': req_path.name,
                                       'clip_sha256': mod.digest(clip),
                                       'request_sha256': mod.digest(req_path),
                                       'start_seconds': 0.0, 'end_seconds': 9.0})
            self.linked.append({'hand_id': hand, 'table_id': table,
                                'game_type_human_declared': game,
                                'candidate_window_seconds': [1.0, 8.0],
                                'clip_window_seconds': [0.0, 9.0],
                                'clip_file': name, 'clip_sha256': mod.digest(clip),
                                'equity_attachment': None, 'ev_attachment': None,
                                'decision_quality_verified': False})
        self.batch_data = {'schema_version': 1,
                           'analysis_status': 'manually_selected_offline_clip_batch_only',
                           'source_video_sha256': video_sha,
                           'source_manifest_sha256': 'b'*64,
                           'video_evidence_verified': False,
                           'automatic_clip_selection_authorized': False,
                           'clip_count': len(self.batch_entries),
                           'clips': self.batch_entries}
        write(self.directory / 'batch_report.json', self.batch_data)
        self.links_data = {'schema_version': 1,
                           'analysis_status': 'offline_clip_hand_provenance_links_only',
                           'source_video_sha256': video_sha,
                           'source_hand_candidates_sha256':
                               self.decision_data['source_hand_candidates_sha256'],
                           'source_batch_report_sha256': mod.digest(self.directory / 'batch_report.json'),
                           'source_batch_manifest_sha256': 'b'*64,
                           'video_evidence_verified': False, 'ev_verified': False,
                           'automatic_clip_selection_authorized': False,
                           'action_recommendation_authorized': False,
                           'clip_count': len(self.linked), 'linked_clips': self.linked}
        write(self.links, self.links_data)

    def run_attach(self, paths=None):
        return mod.attach(self.video, self.links, self.directory, self.output,
                          decision_paths=paths if paths is not None else [self.decision])

    def reject(self):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.run_attach()
        self.assertFalse(self.output.exists())

    def change_decision(self, **updates):
        self.decision_data.update(updates)
        write(self.decision, self.decision_data)

    def change_links(self, **updates):
        self.links_data.update(updates)
        write(self.links, self.links_data)

    def test_valid_attachment(self):
        report = self.run_attach()
        self.assertEqual(report['decision_count'], 1)
        self.assertEqual(report['clip_count'], 1)
        decision = report['clips'][0]['hypothetical_ev_decisions'][0]
        self.assertEqual(decision['decision_id'], self.decision_data['decision_id'])
        self.assertEqual(decision['ev_call_hypothetical'], '37.40')
        self.assertFalse(decision['decision_quality_verified'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertTrue(report['recording_and_exported_clip_hashes_checked'])
        self.assertEqual(json.loads(self.output.read_text()), report)

    def test_two_decisions_same_hand_sorted(self):
        other = self.root / 'second.json'
        second = copy.deepcopy(self.decision_data)
        second['decision_id'] = 'second-decision'
        second['action_pts_seconds'] = 7.0
        write(other, second)
        r = self.run_attach([other, self.decision])
        self.assertEqual(r['decision_count'], 2)
        self.assertEqual([x['action_pts_seconds'] for x in r['clips'][0]['hypothetical_ev_decisions']],
                         [6.0, 7.0])

    def test_four_tables_only_fourth_has_ev(self):
        self.make_batch([(i, f'hand{i}', 'PLO6' if i == 4 else 'PLO5') for i in range(1, 5)])
        self.change_decision(table_id=4, hand_id='hand4', game_type='PLO6')
        r = self.run_attach()
        self.assertEqual(r['clip_count'], 4)
        self.assertEqual([c['decision_count'] for c in r['clips']], [0, 0, 0, 1])

    def test_wrong_table(self):
        self.change_decision(table_id=2)
        self.reject()

    def test_wrong_hand(self):
        self.change_decision(hand_id='other')
        self.reject()

    def test_wrong_game(self):
        self.change_decision(game_type='PLO6')
        self.reject()

    def test_wrong_recording_digest(self):
        self.video.write_bytes(b'tampered recording')
        self.reject()

    def test_wrong_decision_recording_digest(self):
        self.change_decision(recording_sha256='a'*64)
        self.reject()

    def test_wrong_candidate_digest(self):
        self.change_decision(source_hand_candidates_sha256='a'*64)
        self.reject()

    def test_decision_after_hand(self):
        self.change_decision(action_pts_seconds=8.1)
        self.reject()

    def test_decision_before_hand(self):
        self.change_decision(action_pts_seconds=0.9)
        self.reject()

    def test_nan_timestamp(self):
        self.decision.write_text(self.decision.read_text().replace('"action_pts_seconds": 6.0',
                                                                  '"action_pts_seconds": NaN'))
        self.reject()

    def test_boolean_timestamp(self):
        self.change_decision(action_pts_seconds=True)
        self.reject()

    def test_unreviewed_decision(self):
        self.change_decision(recomputed_ev_and_audit_from_supplied_inputs=False)
        self.reject()

    def test_promoted_auto_selection(self):
        self.change_decision(automatic_clip_selection_authorized=True)
        self.reject()

    def test_promoted_action_recommendation(self):
        self.change_decision(action_recommendation_authorized=True)
        self.reject()

    def test_promoted_decision_quality(self):
        self.change_decision(decision_quality_verified=True)
        self.reject()

    def test_missing_provenance_hash(self):
        self.change_decision(source_approval_sha256='not-a-sha')
        self.reject()

    def test_negative_pot(self):
        self.change_decision(pot_before_decision_as_reviewed='-1')
        self.reject()

    def test_invalid_fold_probability(self):
        self.change_decision(fold_probability_hypothesis='1.2')
        self.reject()

    def test_invalid_ev_bound(self):
        self.change_decision(conditional_ev_call_sampling_bounds=['38.00', '56.41'])
        self.reject()

    def test_missing_range_assumption(self):
        self.change_decision(call_range_assumption=' ')
        self.reject()

    def test_duplicate_observation_index(self):
        self.decision_data['reviewed_observation_indices']['action'] = 0
        write(self.decision, self.decision_data)
        self.reject()

    def test_duplicate_decision_report(self):
        with self.assertRaises(ValueError):
            self.run_attach([self.decision, self.decision])
        self.assertFalse(self.output.exists())

    def test_duplicate_decision_id_distinct_files(self):
        second = self.root / 'second.json'
        write(second, self.decision_data)
        with self.assertRaises(ValueError):
            self.run_attach([self.decision, second])
        self.assertFalse(self.output.exists())

    def test_duplicate_json_keys(self):
        self.decision.write_text('{"schema_version":1,"schema_version":1}')
        self.reject()

    def test_clip_tamper(self):
        (self.directory / '01_table1_hand1.mp4').write_bytes(b'tampered')
        self.reject()

    def test_request_tamper(self):
        p = self.directory / '01_request.json'
        p.write_text(p.read_text() + ' ')
        self.reject()

    def test_sidecar_tamper(self):
        p = self.directory / '01_table1_hand1.mp4.json'
        meta = json.loads(p.read_text())
        meta['clip_sha256'] = 'a'*64
        write(p, meta)
        self.reject()

    def test_batch_report_tamper(self):
        self.batch_data['clip_count'] = 9
        write(self.directory / 'batch_report.json', self.batch_data)
        self.reject()

    def test_changed_batch_manifest_digest(self):
        self.batch_data['source_manifest_sha256'] = 'f'*64
        write(self.directory / 'batch_report.json', self.batch_data)
        self.change_links(source_batch_report_sha256=mod.digest(self.directory / 'batch_report.json'))
        self.reject()

    def test_unsafe_clip_filename(self):
        self.linked[0]['clip_file'] = '../bad.mp4'
        write(self.links, self.links_data)
        self.reject()

    def test_cross_hand_clip_window(self):
        self.linked[0]['candidate_window_seconds'] = [6.5, 8.0]
        write(self.links, self.links_data)
        self.reject()

    def test_existing_output_preserved(self):
        self.output.write_text('KEEP')
        with self.assertRaises(ValueError): self.run_attach()
        self.assertEqual(self.output.read_text(), 'KEEP')

    def test_output_inside_batch_rejected(self):
        with self.assertRaises(ValueError):
            mod.attach(self.video, self.links, self.directory,
                       self.directory / 'report.json', decision_paths=[self.decision])

    def test_symlink_decision_rejected(self):
        other = self.root / 'other.json'
        self.decision.rename(other)
        self.decision.symlink_to(other)
        self.reject()

    def test_symlink_clip_rejected(self):
        clip = self.directory / '01_table1_hand1.mp4'
        other = self.root / 'other.mp4'
        clip.rename(other)
        clip.symlink_to(other)
        self.reject()

    def test_no_decisions_rejected(self):
        with self.assertRaises(ValueError): self.run_attach([])
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg not installed')
    def test_real_ffmpeg_synthetic_mp4_bytes(self):
        # FFmpeg verifies the *media* format, not any poker/OCR inference.
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=15',
                        '-t', '10', '-c:v', 'mpeg4', '-q:v', '6', str(self.video)],
                       check=True, capture_output=True)
        clip = self.directory / '01_table1_hand1.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(self.video), '-t', '9', '-vf', 'crop=320:180:0:0',
                        '-an', '-c:v', 'mpeg4', '-q:v', '6', str(clip)],
                       check=True, capture_output=True)
        info = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                               'stream=width,height', '-of', 'json', str(clip)],
                              check=True, capture_output=True, text=True)
        stream = json.loads(info.stdout)['streams'][0]
        self.assertEqual((stream['width'], stream['height']), (320, 180))
        self.change_decision(recording_sha256=mod.digest(self.video))
        self.make_batch([(1, 'hand1', 'PLO5')])
        self.assertEqual(self.run_attach()['decision_count'], 1)


if __name__ == '__main__':
    unittest.main()
