"""Synthetic provenance and failure-closed tests. No actual poker hands are inferred."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_reviewed_clip_hand_links as links


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


class LinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.video = self.root / 'recording.mp4'
        self.video.write_bytes(b'synthetic recording, not a real video')
        self.video_sha = links.sha(self.video)
        self.directory = self.root / 'batch'
        self.directory.mkdir()
        self.hands = self.root / 'hands.json'
        self.manifest = self.root / 'manifest.json'
        self.output = self.root / 'links.json'
        self.equity = self.root / 'equity.json'
        hand = {'hand_id': 'hand1', 'table_id': 1, 'declared_game_type': 'PLO5',
                'start_pts_seconds': 1.0, 'end_pts_seconds': 2.0,
                'boundaries_human_declared_and_visually_checked': True,
                'complete_hand_reconstructed': False, 'ready_for_equity_or_ev': False,
                'observations': [
                    {'reviewed_candidate_index': 0, 'pts_seconds': 1.1,
                     'field': 'hero_cards', 'value': 'As Kd Qh Jc Tc',
                     'source_crop_sha256': 'a'*64},
                    {'reviewed_candidate_index': 1, 'pts_seconds': 1.5,
                     'field': 'board', 'value': '2s 3d 4c',
                     'source_crop_sha256': 'b'*64}]}
        self.hands_data = {'schema_version': 1,
                           'analysis_status': 'human_declared_incomplete_hand_candidates',
                           'recording_sha256': self.video_sha,
                           'complete_hand_reconstructed': False,
                           'automatic_clip_selection_authorized': False,
                           'hands': [hand]}
        self.req = {'schema_version': 1, 'hand_id': 'hand1', 'table_id': 1,
                    'start_seconds': 0.5, 'end_seconds': 2.5,
                    'crop': {'x': 0, 'y': 0, 'width': 320, 'height': 180},
                    'explanation': 'Synthetic manual clip',
                    'source_video_sha256': self.video_sha,
                    'reviewer_confirmed_offline': True}
        self.manifest_data = {'schema_version': 1, 'source_video_sha256': self.video_sha,
                              'reviewer_confirmed_offline': True,
                              'reviewer_note': 'Synthetic only', 'clips': [self.req]}
        self.create_batch()

    def create_batch(self):
        write(self.hands, self.hands_data)
        write(self.manifest, self.manifest_data)
        entries = []
        for i, req in enumerate(self.manifest_data['clips'], 1):
            filename = f'{i:02d}_table{req["table_id"]}_{req["hand_id"]}.mp4'
            clip = self.directory / filename
            clip.write_bytes(f'synthetic clip {i}'.encode())
            request = write(self.directory / f'{i:02d}_request.json', req)
            meta = {'analysis_status': 'manually_selected_offline_clip',
                    'hand_id': req['hand_id'], 'table_id': req['table_id'],
                    'source_video_sha256': self.video_sha,
                    'source_request_sha256': links.sha(request),
                    'clip_sha256': links.sha(clip),
                    'start_seconds': req['start_seconds'],
                    'end_seconds': req['end_seconds'],
                    'crop': req['crop'], 'explanation': req['explanation'],
                    'video_evidence_verified': False,
                    'automatic_clip_selection_authorized': False}
            write(self.directory / (filename + '.json'), meta)
            entries.append({'hand_id': req['hand_id'], 'table_id': req['table_id'],
                            'clip_file': filename, 'sidecar_file': filename + '.json',
                            'request_file': request.name, 'clip_sha256': links.sha(clip),
                            'request_sha256': links.sha(request),
                            'start_seconds': req['start_seconds'],
                            'end_seconds': req['end_seconds']})
        self.batch_data = {'schema_version': 1,
                           'analysis_status': 'manually_selected_offline_clip_batch_only',
                           'source_video_sha256': self.video_sha,
                           'source_manifest_sha256': links.sha(self.manifest),
                           'automatic_clip_selection_authorized': False,
                           'video_evidence_verified': False,
                           'clip_count': len(entries), 'clips': entries}
        write(self.directory / 'batch_report.json', self.batch_data)

    def run_link(self, *, equity=False):
        return links.link(self.video, self.hands, self.manifest, self.directory,
                          self.output, equity_paths=[self.equity] if equity else [])

    def reject(self, action, *, equity=False):
        action()
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.run_link(equity=equity)
        self.assertFalse(self.output.exists())

    def make_equity(self):
        hand = self.hands_data['hands'][0]
        data = {'schema_version': 1,
                'analysis_status': 'reviewed_visible_snapshot_conditional_equity_only',
                'source_hand_candidates_sha256': links.sha(self.hands),
                'recording_sha256': self.video_sha,
                'hand_id': 'hand1', 'table_id': 1, 'game_type': 'PLO5',
                'video_evidence_verified': False, 'complete_hand_reconstructed': False,
                'ready_for_ev': False, 'automatic_clip_selection_authorized': False,
                'hero_hole': hand['observations'][0]['value'].split(),
                'known_board': hand['observations'][1]['value'].split(),
                'hero_evidence': {'source_observation_index': 0, 'pts_seconds': 1.1,
                                  'source_crop_sha256': 'a'*64},
                'board_evidence': {'source_observation_index': 1, 'pts_seconds': 1.5,
                                   'source_crop_sha256': 'b'*64},
                'equity_estimate': 0.45,
                'equity_95pct_hoeffding_interval': [0.35, 0.55],
                'samples': 1000, 'seed': 42,
                'range_assumption': 'Synthetic opponent range'}
        write(self.equity, data)
        return data

    def test_valid_link(self):
        report = self.run_link()
        self.assertEqual(report['clip_count'], 1)
        self.assertEqual(report['linked_clips'][0]['hand_id'], 'hand1')
        self.assertIsNone(report['linked_clips'][0]['equity_attachment'])
        self.assertFalse(report['ev_verified'])
        self.assertTrue(self.output.exists())

    def test_valid_equity_attachment(self):
        self.make_equity()
        report = self.run_link(equity=True)
        eq = report['linked_clips'][0]['equity_attachment']
        self.assertEqual(eq['equity_estimate'], 0.45)
        self.assertFalse(eq['report_authenticity_independently_verified'])

    def test_four_tables(self):
        self.hands_data['hands'] = []
        self.manifest_data['clips'] = []
        for table in range(1, 5):
            hand = copy.deepcopy(self.hands_data.get('_template') or {
                **{'hand_id': 'hand1', 'table_id': 1, 'declared_game_type': 'PLO5',
                   'start_pts_seconds': 1.0, 'end_pts_seconds': 2.0,
                   'boundaries_human_declared_and_visually_checked': True,
                   'complete_hand_reconstructed': False, 'ready_for_equity_or_ev': False,
                   'observations': []}})
            hand['table_id'] = table
            hand['hand_id'] = f'hand{table}'
            self.hands_data['hands'].append(hand)
            req = copy.deepcopy(self.req)
            req['table_id'] = table
            req['hand_id'] = f'hand{table}'
            self.manifest_data['clips'].append(req)
        self.create_batch()
        self.assertEqual(self.run_link()['clip_count'], 4)

    def test_bad_video_hash(self):
        self.reject(lambda: self.video.write_bytes(b'tampered video'))

    def test_bad_manifest_hash(self):
        self.reject(lambda: self.manifest.write_text(self.manifest.read_text() + ' '))

    def test_missing_hand(self):
        self.hands_data['hands'][0]['hand_id'] = 'different'
        self.reject(lambda: write(self.hands, self.hands_data))

    def test_wrong_table(self):
        self.req['table_id'] = 2
        self.manifest_data['clips'][0] = self.req
        self.create_batch()
        self.reject(lambda: None)

    def test_clip_shorter_than_hand(self):
        self.req['end_seconds'] = 1.6
        self.create_batch()
        self.reject(lambda: None)

    def test_excessive_padding(self):
        self.req['end_seconds'] = 30.0
        self.create_batch()
        self.reject(lambda: None)

    def test_clip_tamper(self):
        self.reject(lambda: (self.directory / '01_table1_hand1.mp4').write_bytes(b'changed'))

    def test_sidecar_tamper(self):
        p = self.directory / '01_table1_hand1.mp4.json'
        data = links.read(p)
        data['hand_id'] = 'different'
        self.reject(lambda: write(p, data))

    def test_request_tamper(self):
        p = self.directory / '01_request.json'
        data = links.read(p)
        data['explanation'] = 'Changed'
        self.reject(lambda: write(p, data))

    def test_traversal(self):
        self.batch_data['clips'][0]['clip_file'] = '../escape.mp4'
        self.reject(lambda: write(self.directory / 'batch_report.json', self.batch_data))

    def test_symlink_member(self):
        p = self.directory / '01_table1_hand1.mp4'
        other = self.root / 'other.mp4'
        other.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(other)
        self.reject(lambda: None)

    def test_existing_output(self):
        self.output.write_text('occupied')
        with self.assertRaises(ValueError):
            self.run_link()
        self.assertEqual(self.output.read_text(), 'occupied')

    def test_duplicate_json_keys(self):
        self.reject(lambda: self.hands.write_text('{"a":1,"a":2}'))

    def test_nonfinite_json(self):
        self.reject(lambda: self.manifest.write_text('{"x":NaN}'))

    def test_equity_wrong_source(self):
        data = self.make_equity()
        data['source_hand_candidates_sha256'] = '0'*64
        self.reject(lambda: write(self.equity, data), equity=True)

    def test_equity_wrong_cards(self):
        data = self.make_equity()
        data['hero_hole'][0] = '2c'
        self.reject(lambda: write(self.equity, data), equity=True)

    def test_equity_wrong_crop_hash(self):
        data = self.make_equity()
        data['board_evidence']['source_crop_sha256'] = '0'*64
        self.reject(lambda: write(self.equity, data), equity=True)

    def test_equity_false_verified_claim(self):
        data = self.make_equity()
        data['video_evidence_verified'] = True
        self.reject(lambda: write(self.equity, data), equity=True)

    def test_unselected_equity(self):
        data = self.make_equity()
        data['hand_id'] = 'unknown'
        self.reject(lambda: write(self.equity, data), equity=True)

    def test_duplicate_equity(self):
        self.make_equity()
        with self.assertRaises(ValueError):
            links.link(self.video, self.hands, self.manifest, self.directory,
                       self.output, equity_paths=[self.equity, self.equity])
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
