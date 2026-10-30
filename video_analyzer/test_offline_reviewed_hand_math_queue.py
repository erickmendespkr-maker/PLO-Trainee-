"""Synthetic, offline tests; no real poker footage or live integration."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import offline_reviewed_hand_math_queue as q

PLAN_SHA = 'a' * 64
ANNOT_SHA = 'b' * 64
VIDEO_SHA = 'c' * 64
HERO = ['As', 'Kd', 'Qh', 'Jc', 'Tc']
BOARD = ['2c', '3d', '4h']


def fixture():
    plan = {'schema_version': 1,
            'status': 'human_reviewed_clip_plan_not_automated_hand_detection',
            'source_video_sha256': VIDEO_SHA, 'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H001', 'table_id': 'T1',
                       'start_seconds': 12.0, 'end_seconds': 25.0,
                       'review_basis': 'human_declared_boundaries_not_automatic_detection'},
                      {'hand_id': 'H002', 'table_id': 'T2',
                       'start_seconds': 14.0, 'end_seconds': 23.0,
                       'review_basis': 'human_declared_boundaries_not_automatic_detection'}]}
    hand = {'hand_id': 'H001', 'table_id': 'T1', 'variant': 'PLO5',
            'card_review_status': 'human_confirmed', 'hero_cards': HERO.copy(),
            'board_cards': BOARD.copy(),
            'card_evidence': [{'card': c, 'pts_seconds': 15.0,
                               'source': 'human_frame_review'} for c in HERO + BOARD],
            'opponent_model': {'kind': 'uniform'}, 'iterations': 120,
            'seed': 42, 'pot_now': 100, 'call_cost': 20,
            'reviewer_confidence_declared': .8}
    annotations = {'schema_version': 1, 'source_plan_sha256': PLAN_SHA,
                   'hands': [hand]}
    return plan, annotations


class QueueTests(unittest.TestCase):
    def build(self, plan=None, ann=None):
        p, a = fixture()
        return q.build(plan if plan is not None else p,
                       ann if ann is not None else a, PLAN_SHA, ANNOT_SHA)

    def test_eligible_and_missing_hand(self):
        out = self.build()
        self.assertEqual((out['eligible_count'], out['blocked_count']), (1, 1))
        self.assertEqual(out['entries'][0]['equity_input']['seed'], 42)
        self.assertEqual(out['entries'][1]['blocked_reasons'], ['no_human_annotation'])
        self.assertFalse(out['equity_or_ev_calculated'])
        self.assertFalse(out['action_observed_or_graded'])

    def test_unverified_ocr_is_blocked(self):
        p, a = fixture()
        a['hands'][0]['card_review_status'] = 'ocr_unverified'
        row = self.build(p, a)['entries'][0]
        self.assertIsNone(row['equity_input'])
        self.assertIn('cards_not_human_confirmed', row['blocked_reasons'])

    def test_missing_board_is_blocked(self):
        p, a = fixture()
        del a['hands'][0]['board_cards']
        self.assertIn('incomplete_cards', self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_missing_range_is_blocked(self):
        p, a = fixture()
        del a['hands'][0]['opponent_model']
        self.assertIn('opponent_range_not_supplied', self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_missing_frame_evidence_is_blocked(self):
        p, a = fixture()
        del a['hands'][0]['card_evidence']
        self.assertIn('missing_per_card_frame_evidence', self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_card_evidence_mismatch_is_blocked(self):
        p, a = fixture()
        a['hands'][0]['card_evidence'][0]['card'] = '9s'
        self.assertIn('card_evidence_mismatch', self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_frame_outside_clip_rejected(self):
        p, a = fixture()
        a['hands'][0]['card_evidence'][0]['pts_seconds'] = 26
        with self.assertRaisesRegex(ValueError, 'frame evidence'):
            self.build(p, a)

    def test_card_collision_rejected(self):
        p, a = fixture()
        a['hands'][0]['board_cards'][0] = 'As'
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.build(p, a)

    def test_cross_table_rejected(self):
        p, a = fixture()
        a['hands'][0]['table_id'] = 'T2'
        with self.assertRaisesRegex(ValueError, 'cross-table'):
            self.build(p, a)

    def test_duplicate_hand_rejected(self):
        p, a = fixture()
        a['hands'].append(copy.deepcopy(a['hands'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            self.build(p, a)

    def test_plan_hash_rejected(self):
        p, a = fixture()
        a['source_plan_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'unbound'):
            self.build(p, a)

    def test_weighted_fully_blocked(self):
        p, a = fixture()
        a['hands'][0]['opponent_model'] = {'kind': 'weighted_combos',
            'combos': [{'cards': HERO.copy(), 'weight': 1}]}
        self.assertIn('opponent_range_fully_blocked',
                      self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_weighted_legal_combo(self):
        p, a = fixture()
        a['hands'][0]['opponent_model'] = {'kind': 'weighted_combos',
            'combos': [{'cards': ['5c', '6c', '7c', '8c', '9c'], 'weight': 2}]}
        self.assertEqual(self.build(p, a)['eligible_count'], 1)

    def test_duplicate_weighted_combo_rejected(self):
        p, a = fixture()
        combo = {'cards': ['5c', '6c', '7c', '8c', '9c'], 'weight': 2}
        a['hands'][0]['opponent_model'] = {'kind': 'weighted_combos',
            'combos': [combo, {'cards': list(reversed(combo['cards'])), 'weight': 1}]}
        with self.assertRaisesRegex(ValueError, 'duplicate range'):
            self.build(p, a)

    def test_bool_iterations_rejected(self):
        p, a = fixture()
        a['hands'][0]['iterations'] = True
        self.assertIn('missing_valid_simulation_parameters',
                      self.build(p, a)['entries'][0]['blocked_reasons'])

    def test_nonfinite_and_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.json'
            path.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
                q.read(path)
            path.write_text('{"x":NaN}')
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                q.read(path)

    def test_plo6(self):
        p, a = fixture()
        hand = a['hands'][0]
        hand['variant'] = 'PLO6'
        hand['hero_cards'].append('9s')
        hand['card_evidence'].append({'card': '9s', 'pts_seconds': 17,
                                      'source': 'human_frame_review'})
        self.assertEqual(self.build(p, a)['entries'][0]['equity_input']['variant'], 'PLO6')

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan, ann = fixture()
            plan_path, ann_path, dest = [root / n for n in ('plan.json', 'ann.json', 'queue.json')]
            plan_path.write_text(json.dumps(plan))
            ann['source_plan_sha256'] = q.digest(plan_path)
            ann_path.write_text(json.dumps(ann))
            self.assertEqual(q.main([str(plan_path), str(ann_path), str(dest)]), 0)
            result = json.loads(dest.read_text())
            self.assertEqual(result['source_annotations_sha256'], q.digest(ann_path))
            self.assertEqual(result['eligible_count'], 1)
            with self.assertRaisesRegex(ValueError, 'new JSON'):
                q.main([str(plan_path), str(ann_path), str(dest)])


if __name__ == '__main__':
    unittest.main()
