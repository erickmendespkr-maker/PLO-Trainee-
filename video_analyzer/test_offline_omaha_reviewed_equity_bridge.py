"""Synthetic, offline fail-closed bridge tests. No actual video or OCR claims."""
import json
from pathlib import Path
import tempfile
import unittest

import offline_four_table_action_timeline_audit as audit
import offline_omaha_reviewed_equity_bridge as bridge


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')


def candidate(game='PLO5'):
    hero = 'As Ad Kh Qh Jc' + (' Tc' if game == 'PLO6' else '')
    observations = [
        {'reviewed_candidate_index': 0, 'pts_seconds': 1.0, 'field': 'hero_cards',
         'value': hero, 'source_crop_sha256': 'a'*64, 'source_crop_path': 'tables/t1.png',
         'review_decision': 'correct'},
        {'reviewed_candidate_index': 1, 'pts_seconds': 2.0, 'field': 'board',
         'value': '2c 7d 9s', 'source_crop_sha256': 'b'*64,
         'source_crop_path': 'tables/t1.png', 'review_decision': 'correct'},
        {'reviewed_candidate_index': 2, 'pts_seconds': 3.0, 'field': 'action',
         'value': 'check', 'source_crop_sha256': 'c'*64,
         'source_crop_path': 'tables/t1.png', 'review_decision': 'confirm'},
    ]
    hand = {'hand_id': 'h1', 'table_id': 1, 'declared_game_type': game,
            'start_pts_seconds': 0.0, 'end_pts_seconds': 10.0,
            'boundaries_human_declared_and_visually_checked': True,
            'observations': observations, 'missing_observed_fields': ['pot'],
            'changing_card_fields_needing_street_review': [],
            'same_timestamp_card_collisions': [],
            'complete_hand_reconstructed': False, 'ready_for_equity_or_ev': False,
            'status': 'incomplete_hand_candidate_requires_action_history_and_ranges'}
    return {'schema_version': 1, 'analysis_status': 'human_declared_incomplete_hand_candidates',
            'recording_sha256': 'd'*64, 'source_reviewed_fields_sha256': 'e'*64,
            'hand_windows_manifest_sha256': 'f'*64,
            'source_region_samples_sha256': '0'*64, 'hands': [hand],
            'complete_hand_reconstructed': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False, 'warning': 'Synthetic only'}


def approval(game='PLO5'):
    return {'schema_version': 1, 'source_hand_candidates_sha256': '',
            'source_action_audit_sha256': '', 'reviewer_confirmed_offline': True,
            'hand_id': 'h1', 'table_id': 1,
            'hero_observation_index': 0, 'board_observation_index': 1,
            'explicit_villain_hands': [
                ['3c', '4d', '5h', '6s', '8c'] + (['8d'] if game == 'PLO6' else [])],
            'range_assumption': 'One synthetic fixed opponent combination; unobserved',
            'samples': 100, 'seed': 42, 'reviewer_note': 'Synthetic human declaration'}


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.h = self.root/'hands.json'
        self.a = self.root/'audit.json'
        self.p = self.root/'approval.json'
        self.o = self.root/'report.json'
        self.game = 'PLO5'
        self.prepare()

    def prepare(self, game='PLO5'):
        self.game = game
        write(self.h, candidate(game))
        if self.a.exists(): self.a.unlink()
        audit.build(self.h, self.a)
        self.ap = approval(game)
        self.bind()

    def bind(self):
        self.ap['source_hand_candidates_sha256'] = bridge.sha(self.h)
        self.ap['source_action_audit_sha256'] = bridge.sha(self.a)
        write(self.p, self.ap)

    def run_bridge(self):
        return bridge.bridge(self.h, self.a, self.p, self.o)

    def assert_rejected(self):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.run_bridge()
        self.assertFalse(self.o.exists())

    def test_plo5_snapshot(self):
        r = self.run_bridge()
        self.assertEqual(r['game_type'], 'PLO5')
        self.assertEqual(r['samples'], r['wins'] + r['ties'] + r['losses'])
        self.assertEqual(r['hero_evidence']['source_observation_index'], 0)
        self.assertEqual(r['board_evidence']['pts_seconds'], 2)
        self.assertFalse(r['video_evidence_verified'])
        self.assertFalse(r['ready_for_ev'])
        self.assertFalse(r['complete_hand_reconstructed'])
        self.assertFalse(r['automatic_clip_selection_authorized'])
        self.assertEqual(json.loads(self.o.read_text()), r)

    def test_plo6_snapshot(self):
        self.prepare('PLO6')
        r = self.run_bridge()
        self.assertEqual(len(r['hero_hole']), 6)
        self.assertEqual(r['game_type'], 'PLO6')

    def test_deterministic_seed(self):
        first = self.run_bridge()
        self.o.unlink()
        second = self.run_bridge()
        self.assertEqual(first, second)

    def test_reject_unapproved(self):
        self.ap['reviewer_confirmed_offline'] = False
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_stale_hands_hash(self):
        self.ap['source_hand_candidates_sha256'] = '0'*64
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_stale_audit_hash(self):
        self.ap['source_action_audit_sha256'] = '0'*64
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_modified_audit(self):
        a = json.loads(self.a.read_text())
        a['hands'][0]['review_flags'] = [{'code': 'invented', 'pts_seconds': None}]
        write(self.a, a)
        self.bind()
        self.assert_rejected()

    def test_reject_wrong_field(self):
        self.ap['hero_observation_index'] = 2
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_wrong_table(self):
        self.ap['table_id'] = 2
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_bool_index(self):
        self.ap['hero_observation_index'] = True
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_duplicate_cards_range(self):
        self.ap['explicit_villain_hands'][0][0] = 'As'
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_missing_range_assumption(self):
        self.ap['range_assumption'] = ' '
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_unbounded_samples(self):
        self.ap['samples'] = 10001
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_extra_manifest_key(self):
        self.ap['authorize_clips'] = True
        write(self.p, self.ap)
        self.assert_rejected()

    def test_reject_duplicate_json_keys(self):
        self.p.write_text(self.p.read_text().replace('"seed": 42', '"seed": 42, "seed": 43'))
        self.assert_rejected()

    def test_reject_existing_output(self):
        self.o.write_text('do not overwrite')
        with self.assertRaises(ValueError): self.run_bridge()
        self.assertEqual(self.o.read_text(), 'do not overwrite')

    def test_reject_symlinked_manifest(self):
        alias = self.root/'alias.json'
        alias.symlink_to(self.p)
        with self.assertRaises(ValueError): bridge.bridge(self.h, self.a, alias, self.o)
        self.assertFalse(self.o.exists())

    def test_reject_wrong_recording(self):
        recording = self.root/'sample.mp4'
        recording.write_bytes(b'not the recording')
        with self.assertRaises(ValueError):
            bridge.bridge(self.h, self.a, self.p, self.o, recording_path=recording)
        self.assertFalse(self.o.exists())

    def test_reject_conflicting_hero_cards(self):
        data = candidate()
        data['hands'][0]['observations'].append({
            'reviewed_candidate_index': 3, 'pts_seconds': 4.0,
            'field': 'hero_cards', 'value': 'As Ad Kh Qh Tc',
            'source_crop_sha256': 'a'*64, 'source_crop_path': 'tables/t1.png',
            'review_decision': 'correct'})
        write(self.h, data)
        self.a.unlink()
        audit.build(self.h, self.a)
        self.bind()
        self.assert_rejected()

    def test_reject_board_collision(self):
        data = candidate()
        data['hands'][0]['observations'][1]['value'] = 'As 7d 9s'
        write(self.h, data)
        self.a.unlink()
        audit.build(self.h, self.a)
        self.bind()
        self.assert_rejected()

    def test_reject_unreviewed_observation(self):
        data = candidate()
        data['hands'][0]['observations'][0]['review_decision'] = 'reject'
        write(self.h, data)
        self.assert_rejected()

    def test_reject_unsupported_game(self):
        data = candidate()
        data['hands'][0]['declared_game_type'] = 'PLO4'
        write(self.h, data)
        self.assert_rejected()


if __name__ == '__main__': unittest.main()
