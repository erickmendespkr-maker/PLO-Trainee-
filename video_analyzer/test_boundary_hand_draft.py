"""Synthetic-only fail-closed tests for navigation-to-hand-review drafts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from boundary_history_bridge import build
from boundary_hand_draft import (build_template, validate_review,
                                 export_template, export_review)
from test_boundary_history_bridge import fixture


def example():
    packet, labels = fixture()
    packet['tasks'].append({'task_id': 'interior', 'table_id': 1,
                            'window_start_seconds': 1.5,
                            'window_end_seconds': 1.7, 'frames': []})
    navigation = build(packet, labels, 'b' * 64)
    return navigation, 'c' * 64


def edited_example():
    nav, sha = example()
    edited = build_template(nav, sha)
    row = edited['entries'][0]
    row['reviewer'] = 'synthetic reviewer'
    row['fields']['variant'] = {
        'value': 'PLO5', 'confidence': .95, 'source_pts_seconds': 1.3,
        'source_kind': 'manual_video_review', 'human_confirmed': True}
    row['fields']['hero_cards_visible'] = {
        'value': ['As', 'Kd', 'Qc', 'Jh', 'Ts'], 'confidence': .8,
        'source_pts_seconds': 2.0, 'source_kind': 'manual_video_review',
        'human_confirmed': True}
    row['fields']['board_visible'] = {
        'value': ['2s', '3d', '4c'], 'confidence': .3,
        'source_pts_seconds': None, 'source_kind': 'hypothesis',
        'human_confirmed': False}
    row['actions'] = [{
        'timestamp_seconds': 2.1, 'actor': 'hero', 'action': 'call',
        'amount': None, 'confidence': .6, 'source_kind': 'manual_video_review',
        'human_confirmed': True}]
    return nav, sha, edited


class DraftTests(unittest.TestCase):
    def test_four_tables_unknown_and_unresolved(self):
        nav, sha = example()
        template = build_template(nav, sha)
        self.assertEqual(len(template['entries']), 4)
        self.assertTrue(template['entries'][0]['contains_unresolved_interior_candidates'])
        self.assertEqual(template['entries'][0]['interior_candidate_ids'], ['interior'])
        self.assertEqual([x['table_id'] for x in template['entries']], [1, 2, 3, 4])
        self.assertTrue(all(x['hand_id'] is None and not x['actions'] for x in template['entries']))
        self.assertTrue(all(f['value'] is None for x in template['entries'] for f in x['fields'].values()))
        self.assertFalse(template['ready_for_equity_or_ev'])

    def test_review_preserves_math_block(self):
        nav, sha, edited = edited_example()
        result = validate_review(nav, sha, edited)
        self.assertEqual(result['counts']['human_confirmed_fields'], 2)
        self.assertEqual(result['counts']['human_reported_actions'], 1)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['cards_or_actions_verified'])
        self.assertEqual(result['entries'][0]['fields']['board_visible']['source_kind'], 'hypothesis')

    def test_reject_root_authority_escalation(self):
        nav, sha, edited = edited_example()
        edited['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_span_metadata_tampering(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['start_human_seconds'] = 0
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_forged_navigation_authority(self):
        nav, sha = example()
        nav['cards_or_actions_verified'] = True
        with self.assertRaises(ValueError):
            build_template(nav, sha)

    def test_reject_bad_variant_card_count(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['fields']['hero_cards_visible']['value'].pop()
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_duplicate_board_private_card(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['fields']['board_visible']['value'][0] = 'As'
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_out_of_span_evidence(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['fields']['variant']['source_pts_seconds'] = 200
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_unconfirmed_human_claim(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['fields']['variant']['source_kind'] = 'hypothesis'
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_bad_confidence_and_nan(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['fields']['variant']['confidence'] = float('nan')
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_action_order_and_unknown_action(self):
        nav, sha, edited = edited_example()
        a = copy.deepcopy(edited['entries'][0]['actions'][0])
        a['timestamp_seconds'] = 1.8
        edited['entries'][0]['actions'].append(a)
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)
        edited['entries'][0]['actions'] = [a]
        a['action'] = 'auto_bet'
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_missing_reviewer_per_entry(self):
        nav, sha, edited = edited_example()
        edited['entries'][0]['reviewer'] = ''
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_reject_invalid_navigation_overlap(self):
        nav, sha = example()
        nav['candidate_spans'].append(copy.deepcopy(nav['candidate_spans'][0]))
        with self.assertRaises(ValueError):
            build_template(nav, sha)

    def test_reject_missing_fields(self):
        nav, sha, edited = edited_example()
        del edited['entries'][0]['fields']['variant']
        with self.assertRaises(ValueError):
            validate_review(nav, sha, edited)

    def test_files_roundtrip_and_no_overwrite(self):
        nav, _, _ = edited_example()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            n, t, r = (root / x for x in ('navigation.json', 'template.json', 'review.json'))
            n.write_text(json.dumps(nav))
            generated = export_template(n, t)
            self.assertEqual(json.loads(t.read_text()), generated)
            with self.assertRaises(ValueError):
                export_template(n, t)
            edited = copy.deepcopy(generated)
            edited['entries'][0]['reviewer'] = 'synthetic'
            edited['entries'][0]['fields']['pot_observed'] = {
                'value': 42, 'confidence': .7, 'source_pts_seconds': 2.0,
                'source_kind': 'manual_video_review', 'human_confirmed': True}
            e = root / 'edited.json'
            e.write_text(json.dumps(edited))
            validated = export_review(n, e, r)
            self.assertEqual(json.loads(r.read_text()), validated)
            self.assertFalse(validated['ready_for_equity_or_ev'])
            with self.assertRaises(ValueError):
                export_review(n, e, r)

    def test_file_rejects_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            n, t = root / 'navigation.json', root / 'template.json'
            n.write_text('{"schema_version":2,"schema_version":2}')
            with self.assertRaises(ValueError):
                export_template(n, t)
            self.assertFalse(t.exists())

    def test_navigation_digest_binding(self):
        nav, sha, edited = edited_example()
        with self.assertRaises(ValueError):
            validate_review(nav, 'f' * 64, edited)


if __name__ == '__main__':
    unittest.main()
