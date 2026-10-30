"""Synthetic offline OCR review bridge tests. No real session video."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_ocr_review_bridge as bridge
import offline_reviewed_hand_math_queue as queue


def fixture():
    plan = {'schema_version': 1,
            'status': 'human_reviewed_clip_plan_not_automated_hand_detection',
            'source_video_sha256': 'a'*64, 'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H1', 'table_id': 'T1', 'start_seconds': 10,
                       'end_seconds': 20,
                       'review_basis': 'human_declared_boundaries_not_automatic_detection'},
                      {'hand_id': 'H2', 'table_id': 'T2', 'start_seconds': 11,
                       'end_seconds': 21,
                       'review_basis': 'human_declared_boundaries_not_automatic_detection'}]}
    obs = {'hand_id': 'H1', 'table_id': 'T1', 'field': 'hero_card', 'slot': 0,
           'value': 'As', 'pts_seconds': 12, 'confidence': 1,
           'roi': {'x': .1, 'y': .2, 'w': .2, 'h': .2}, 'engine': 'synthetic'}
    proposals = {'schema_version': 1, 'status': 'offline_ocr_proposals_unverified',
                 'source_plan_sha256': 'b'*64,
                 'source_video_sha256_claim': 'a'*64, 'observations': [obs]}
    return plan, proposals


class ReviewBridgeTests(unittest.TestCase):
    def build(self, modifier=None):
        p, r = fixture()
        if modifier:
            modifier(p, r)
        return bridge.build(p, r, 'b'*64, 'c'*64)

    def test_no_automatic_promotion_even_perfect_confidence(self):
        worksheet, annotations = self.build()
        self.assertFalse(worksheet['card_claims_verified'])
        self.assertFalse(worksheet['equity_or_ev_calculated'])
        self.assertTrue(worksheet['hands'][0]['human_review_required'])
        self.assertEqual(annotations['hands'][0]['card_review_status'], 'ocr_unverified')
        result = queue.build(fixture()[0], annotations, 'b'*64, 'c'*64)
        self.assertEqual((result['eligible_count'], result['blocked_count']), (0, 2))

    def test_empty_hand_retained(self):
        w, a = self.build()
        self.assertEqual(w['hands'][1]['review_flags'], ['no_ocr_observations'])
        self.assertEqual(len(a['hands']), 1)

    def test_multiple_tables_and_sorted_timestamp(self):
        def add(p, r):
            x = copy.deepcopy(r['observations'][0]); x.update(hand_id='H2', table_id='T2', pts_seconds=15)
            r['observations'].insert(0, x)
        w, a = self.build(add)
        self.assertEqual(len(a['hands']), 2)
        self.assertEqual([x['table_id'] for x in w['hands']], ['T1', 'T2'])

    def test_conflicting_slot_flag(self):
        def add(p, r):
            x = copy.deepcopy(r['observations'][0]); x['value'] = 'Kh'
            r['observations'].append(x)
        self.assertIn('conflicting_slot_candidates', self.build(add)[0]['hands'][0]['review_flags'])

    def test_duplicate_card_flag(self):
        def add(p, r):
            x = copy.deepcopy(r['observations'][0]); x['slot'] = 1
            r['observations'].append(x)
        self.assertIn('same_card_proposed_in_multiple_slots', self.build(add)[0]['hands'][0]['review_flags'])

    def test_bad_card_text_flag_not_error(self):
        def add(p, r): r['observations'][0]['value'] = 'A?' 
        self.assertIn('unrecognized_card_text', self.build(add)[0]['hands'][0]['review_flags'])

    def test_low_confidence_flag(self):
        def add(p, r): r['observations'][0]['confidence'] = .4
        self.assertIn('low_raw_ocr_confidence', self.build(add)[0]['hands'][0]['review_flags'])

    def test_cross_table_rejected(self):
        def add(p, r): r['observations'][0]['table_id'] = 'T2'
        with self.assertRaisesRegex(ValueError, 'cross-table'): self.build(add)

    def test_outside_timestamp_rejected(self):
        def add(p, r): r['observations'][0]['pts_seconds'] = 25
        with self.assertRaisesRegex(ValueError, 'timestamp'): self.build(add)

    def test_bad_roi_rejected(self):
        def add(p, r): r['observations'][0]['roi']['x'] = .95
        with self.assertRaisesRegex(ValueError, 'ROI'): self.build(add)

    def test_bool_confidence_rejected(self):
        def add(p, r): r['observations'][0]['confidence'] = True
        with self.assertRaisesRegex(ValueError, 'confidence'): self.build(add)

    def test_nan_confidence_rejected(self):
        def add(p, r): r['observations'][0]['confidence'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'confidence'): self.build(add)

    def test_unbound_plan_rejected(self):
        def add(p, r): r['source_plan_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'unbound'): self.build(add)

    def test_unbound_video_rejected(self):
        def add(p, r): r['source_video_sha256_claim'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'unbound'): self.build(add)

    def test_unexpected_field_rejected(self):
        def add(p, r): r['observations'][0]['unsafe'] = 'anything'
        with self.assertRaisesRegex(ValueError, 'fields'): self.build(add)

    def test_oversized_observation_list_rejected(self):
        def add(p, r): r['observations'] = r['observations'] * 6001
        with self.assertRaisesRegex(ValueError, 'unbound'): self.build(add)

    def test_non_card_slot_rejected(self):
        def add(p, r): r['observations'][0].update(field='pot', slot=0)
        with self.assertRaisesRegex(ValueError, 'slot'): self.build(add)

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan, proposals = fixture()
            p, r, w, a = [root / x for x in ('plan.json', 'ocr.json', 'worksheet.json', 'annotations.json')]
            p.write_text(json.dumps(plan)); proposals['source_plan_sha256'] = queue.digest(p)
            r.write_text(json.dumps(proposals))
            self.assertEqual(bridge.main([str(p), str(r), str(w), str(a)]), 0)
            self.assertEqual(json.loads(w.read_text())['source_proposals_sha256'], queue.digest(r))
            self.assertEqual(json.loads(a.read_text())['hands'][0]['card_review_status'], 'ocr_unverified')
            with self.assertRaisesRegex(ValueError, 'new JSON'): bridge.main([str(p), str(r), str(w), str(a)])

    def test_output_same_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(ValueError, 'distinct new JSON'):
                bridge.main([str(root/'x.json'), str(root/'y.json'), str(root/'z.json'), str(root/'z.json')])

    def test_four_tables(self):
        def add(p, r):
            for n in (3, 4):
                p['clips'].append({'hand_id': 'H'+str(n), 'table_id': 'T'+str(n),
                    'start_seconds': 12, 'end_seconds': 19,
                    'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        self.assertEqual(len(self.build(add)[0]['hands']), 4)


if __name__ == '__main__':
    unittest.main()
