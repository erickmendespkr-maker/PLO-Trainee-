"""Synthetic regression tests: human-reviewed observations remain uncertain."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from activity_reviewed_hand_timeline import (build_reviewed_hand_timeline,
                                             write_reviewed_hand_timeline)
from activity_snapshot_chain import canonical_sha256
from hand_history import Observation

PTS = 'decoded_filtergraph_pts_not_capture_time'
HERO = ('As', 'Ks', '2d', '3c', '4h')


def fixture():
    observations, provenance = [], []

    def add(table, hand, timestamp, action, *, board=None, hero=None, pot=None, variant='PLO5'):
        fields = {name: .9 for name, val in [('board', board), ('hero_cards', hero), ('pot', pot)]
                  if val is not None}
        obs = Observation(table, timestamp, action, .92, hand, variant=variant,
                          board=board, hero_cards=hero, pot=pot, field_confidence=fields)
        index = len(observations)
        observations.append(asdict(obs))
        evidence = []
        for name, val in [('board', board), ('hero_cards', hero), ('pot', pot)]:
            if val is not None:
                evidence.append({'field': name, 'candidate_index': index*10 + len(evidence),
                                 'source_image': f'table{table}/frame{index}.png',
                                 'source_timestamp': timestamp,
                                 'source_timestamp_semantics': PTS,
                                 'approved_value': list(val) if isinstance(val, tuple) else val,
                                 'reviewer_confidence': .9})
        provenance.append({'event_index': index, 'table_id': table, 'timestamp': timestamp,
                           'hand_id': hand, 'human_confirmed': True, 'evidence': evidence})
    for table in (1, 2, 3, 4):
        add(table, f'h{table}', 0, 'hand_start', hero=HERO, pot=20)
        add(table, f'h{table}', 1, 'board', board=('Qs', 'Js', 'Ts'))
        add(table, f'h{table}', 2, 'call')
        add(table, f'h{table}', 3, 'board', board=('Qs', 'Js', 'Ts', '9d'))
        add(table, f'h{table}', 4, 'hand_end')
    return {'schema_version': 1, 'analysis_status': 'human_reviewed_activity_observations',
            'ready_for_equity_or_ev': False, 'timestamp_semantics': PTS,
            'recording_sha256': 'a'*64, 'evidence_manifest_sha256': 'b'*64,
            'ocr_report_sha256': 'c'*64, 'observations': observations, 'provenance': provenance}


class ReviewedTimelineTests(unittest.TestCase):
    def test_four_tables_provenance_and_board_extension(self):
        out = build_reviewed_hand_timeline(fixture())
        self.assertEqual(out['counts']['hands_human_assigned'], 4)
        self.assertEqual(out['counts']['hands_with_review_flags'], 0)
        for hand in out['hands']:
            events = hand['events']
            self.assertEqual(events[3]['board_transition']['kind'], 'compatible_extension')
            self.assertEqual(events[3]['board_transition']['from_timestamp'], 1)
            self.assertEqual(events[3]['board_transition']['to_timestamp'], 3)
            self.assertFalse(events[3]['board_transition']['exact_change_time_known'])
            self.assertEqual(events[1]['field_evidence']['board']['decoded_source_pts'], 1)
            self.assertEqual(events[1]['visible_street_hint'], 'flop_visible_board')
            self.assertEqual(events[3]['visible_street_hint'], 'turn_visible_board')
            self.assertIsNone(events[2]['board_visible'])
            self.assertFalse(out['ready_for_equity_or_ev'])
            self.assertFalse(out['automatic_clip_selection_authorized'])

    def test_incompatible_board_flags_not_new_hand(self):
        f = fixture()
        f['observations'][3]['board'] = ('Qs', 'Js', '8c', '9d')
        f['provenance'][3]['evidence'][0]['approved_value'] = ['Qs', 'Js', '8c', '9d']
        out = build_reviewed_hand_timeline(f)
        self.assertIn('incompatible_board_progression_requires_review', out['hands'][0]['review_flags'])
        self.assertEqual(out['counts']['hands_human_assigned'], 4)

    def test_same_pts_board_conflict_flagged(self):
        f = fixture()
        f['observations'][3]['timestamp'] = 1
        f['provenance'][3]['timestamp'] = 1
        f['provenance'][3]['evidence'][0]['source_timestamp'] = 1
        # Other events on same table at t=2 would be out of order; shift the call.
        f['observations'][2]['timestamp'] = 1
        f['provenance'][2]['timestamp'] = 1
        out = build_reviewed_hand_timeline(f)
        self.assertIn('same_pts_conflicting_board_observations', out['hands'][0]['review_flags'])

    def test_private_card_change_requires_review(self):
        f = fixture()
        f['observations'][3]['hero_cards'] = ('Ah', 'Ks', '2d', '3c', '4h')
        f['observations'][3]['field_confidence']['hero_cards'] = .9
        f['provenance'][3]['evidence'].append({
            'field': 'hero_cards', 'candidate_index': 999, 'source_image': 'x.png',
            'source_timestamp': 3, 'source_timestamp_semantics': PTS,
            'approved_value': ['Ah', 'Ks', '2d', '3c', '4h'], 'reviewer_confidence': .9})
        out = build_reviewed_hand_timeline(f)
        self.assertIn('private_cards_changed_within_hand', out['hands'][0]['review_flags'])

    def test_unassigned_not_guessed(self):
        f = fixture()
        f['observations'][2]['hand_id'] = None
        f['provenance'][2]['hand_id'] = None
        out = build_reviewed_hand_timeline(f)
        self.assertEqual(out['counts']['unassigned_observations'], 1)
        self.assertEqual(out['unassigned_observations'][0]['observation_index'], 2)
        self.assertEqual(out['unassigned_observations'][0]['human_annotated_action'], 'call')

    def test_end_without_start_and_missing_end(self):
        f = fixture()
        f['observations'][0]['action'] = 'board'
        f['observations'][4]['action'] = 'check'
        out = build_reviewed_hand_timeline(f)
        self.assertIn('hand_start_not_observed', out['hands'][0]['review_flags'])
        self.assertIn('hand_end_not_observed', out['hands'][0]['review_flags'])

    def test_reject_provenance_tampering(self):
        f = fixture()
        f['provenance'][1]['evidence'][0]['source_timestamp'] = 4
        with self.assertRaises(ValueError):
            build_reviewed_hand_timeline(f)

    def test_reject_hash_mismatch(self):
        f = fixture()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_reviewed_hand_timeline(f, expected_review_sha256='0'*64)

    def test_reject_unreviewed_source(self):
        f = fixture()
        f['analysis_status'] = 'unverified_ocr_candidates_only'
        with self.assertRaises(ValueError):
            build_reviewed_hand_timeline(f)

    def test_file_roundtrip_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'input.json', Path(d)/'timeline.json'
            f = fixture()
            src.write_text(json.dumps(f), encoding='utf-8')
            out = write_reviewed_hand_timeline(src, dst,
                                                expected_review_sha256=canonical_sha256(f))
            self.assertEqual(json.loads(dst.read_text())['counts'], out['counts'])
            with self.assertRaises(ValueError):
                write_reviewed_hand_timeline(src, dst)
            with self.assertRaises(ValueError):
                write_reviewed_hand_timeline(src, src)

    def test_no_future_board_borrowed(self):
        out = build_reviewed_hand_timeline(fixture())
        self.assertIsNone(out['hands'][0]['events'][2]['board_visible'])
        self.assertIsNone(out['hands'][0]['events'][2]['visible_street_hint'])

    def test_interleaved_hand_ids_are_not_merged_silently(self):
        f = fixture()
        # A hand label returning after another hand is a human-review conflict.
        f['observations'][1]['hand_id'] = 'other'
        f['provenance'][1]['hand_id'] = 'other'
        out = build_reviewed_hand_timeline(f)
        h = next(x for x in out['hands'] if x['table_id'] == 1 and x['hand_id_human_assigned'] == 'h1')
        self.assertIn('interleaved_hand_identity_requires_review', h['review_flags'])

    def test_board_private_collision_across_frames(self):
        f = fixture()
        f['observations'][1]['board'] = ('As', 'Js', 'Ts')
        f['provenance'][1]['evidence'][0]['approved_value'] = ['As', 'Js', 'Ts']
        out = build_reviewed_hand_timeline(f)
        self.assertIn('visible_board_private_card_collision', out['hands'][0]['review_flags'])

    def test_variant_change_is_review_flag_not_equity(self):
        f = fixture()
        f['observations'][3]['variant'] = 'PLO6'
        out = build_reviewed_hand_timeline(f)
        self.assertIn('variant_changed_within_hand', out['hands'][0]['review_flags'])
        self.assertFalse(out['ready_for_equity_or_ev'])

    def test_input_is_not_modified(self):
        f = fixture()
        original = copy.deepcopy(f)
        build_reviewed_hand_timeline(f)
        self.assertEqual(f, original)


if __name__ == '__main__':
    unittest.main()
