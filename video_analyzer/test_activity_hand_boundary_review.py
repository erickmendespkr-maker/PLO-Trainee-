"""Synthetic checks: hand-boundary windows remain uncertain and EV-blocked."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from activity_hand_boundary_review import (build_hand_boundary_review,
                                           write_hand_boundary_review)
from activity_reviewed_hand_timeline import build_reviewed_hand_timeline
from activity_snapshot_chain import canonical_sha256
from hand_history import Observation
from test_activity_reviewed_hand_timeline import fixture


def timeline(*, with_unassigned=False):
    reviewed = fixture()
    def add(timestamp, action, hand_id):
        index = len(reviewed['observations'])
        obs = Observation(1, timestamp, action, .92, hand_id, variant='PLO5')
        reviewed['observations'].append(asdict(obs))
        reviewed['provenance'].append({
            'event_index': index, 'table_id': 1, 'timestamp': timestamp,
            'hand_id': hand_id, 'human_confirmed': True, 'evidence': []})
    if with_unassigned:
        add(5, 'check', None)
    add(6, 'hand_start', 'second')
    add(7, 'hand_end', 'second')
    return build_reviewed_hand_timeline(reviewed)


def hints():
    return {'schema_version': 1, 'analysis_status': 'unverified_boundary_hints_only',
            'requires_manual_review': True,
            'boundary_hints': [{'table_id': 1, 'field': 'hero_cards', 'timestamp': 5.5,
                                'reason': 'changed_private_cards',
                                'status': 'needs_manual_review', 'human_confirmed': False}]}


class BoundaryReviewTests(unittest.TestCase):
    def test_four_tables_one_review_window(self):
        result = build_hand_boundary_review(timeline())
        self.assertEqual(result['counts']['observed_human_assigned_hands'], 5)
        self.assertEqual(result['counts']['inter_hand_windows'], 1)
        w = result['inter_hand_review_windows'][0]
        self.assertEqual((w['table_id'], w['candidate_interval_pts']), (1, [4, 6]))
        self.assertEqual(w['status'], 'review_interval_available_not_confirmed')
        self.assertFalse(w['exact_boundary_known'])
        self.assertFalse(result['automatic_hand_boundaries_authorized'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['strategic_error_established'])

    def test_one_hand_per_table_produces_no_boundaries(self):
        result = build_hand_boundary_review(build_reviewed_hand_timeline(fixture()))
        self.assertEqual(result['counts']['inter_hand_windows'], 0)
        self.assertEqual(len(result['observed_hand_spans']), 4)

    def test_unassigned_observation_blocks_clear_window(self):
        result = build_hand_boundary_review(timeline(with_unassigned=True))
        w = result['inter_hand_review_windows'][0]
        self.assertEqual(w['unassigned_observation_indices'], [20])
        self.assertEqual(w['status'], 'manual_resolution_required')
        self.assertIn('unassigned_observations_in_interval', w['review_reasons'])

    def test_hints_only_context_not_confirmation(self):
        t = timeline()
        h = hints()
        h['recording_sha256'] = t['recording_sha256']
        result = build_hand_boundary_review(t, h)
        w = result['inter_hand_review_windows'][0]
        self.assertEqual(len(w['unverified_ocr_hints']), 1)
        self.assertEqual(w['unverified_ocr_hints'][0]['status'], 'unverified_not_confirmation')
        self.assertFalse(w['exact_boundary_known'])
        self.assertTrue(w['unverified_ocr_hints'][0]['recording_identity_bound'])
        self.assertTrue(result['hints_recording_identity_bound'])
        self.assertEqual(result['source_boundary_hints_sha256'], canonical_sha256(h))

    def test_unbound_hints_explicitly_marked(self):
        result = build_hand_boundary_review(timeline(), hints())
        self.assertFalse(result['hints_recording_identity_bound'])
        self.assertFalse(result['inter_hand_review_windows'][0]['unverified_ocr_hints'][0]['recording_identity_bound'])

    def test_wrong_recording_hints_rejected(self):
        h = hints()
        h['recording_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'recording SHA-256 mismatch'):
            build_hand_boundary_review(timeline(), h)

    def test_wrong_expected_timeline_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Timeline SHA-256 mismatch'):
            build_hand_boundary_review(timeline(), expected_timeline_sha256='f'*64)

    def test_tampered_timeline_with_pin_rejected(self):
        t = timeline()
        pin = canonical_sha256(t)
        t['hands'][0]['events'][0]['timestamp'] = .5
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_hand_boundary_review(t, expected_timeline_sha256=pin)

    def test_tampered_observed_span_rejected_without_pin(self):
        t = timeline()
        t['hands'][0]['last_observed_pts'] = 99
        with self.assertRaisesRegex(ValueError, 'Inconsistent observed hand span'):
            build_hand_boundary_review(t)

    def test_reject_ev_authorization(self):
        t = timeline()
        t['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_hand_boundary_review(t)

    def test_gap_too_large_requires_manual_resolution(self):
        result = build_hand_boundary_review(timeline(), max_gap_seconds=1)
        w = result['inter_hand_review_windows'][0]
        self.assertIsNotNone(w['candidate_interval_pts'])
        self.assertIn('gap_exceeds_review_window_limit', w['review_reasons'])
        self.assertEqual(w['status'], 'manual_resolution_required')

    def test_overlap_never_proposes_interval(self):
        t = timeline()
        second = next(h for h in t['hands'] if h['hand_id_human_assigned'] == 'second')
        second['events'][0]['timestamp'] = 3
        second['first_observed_pts'] = 3
        result = build_hand_boundary_review(t)
        w = result['inter_hand_review_windows'][0]
        self.assertIsNone(w['candidate_interval_pts'])
        self.assertIn('overlapping_human_hand_assignments', w['review_reasons'])

    def test_same_pts_not_exact_boundary(self):
        t = timeline()
        second = next(h for h in t['hands'] if h['hand_id_human_assigned'] == 'second')
        second['events'][0]['timestamp'] = 4
        second['first_observed_pts'] = 4
        w = build_hand_boundary_review(t)['inter_hand_review_windows'][0]
        self.assertIsNone(w['candidate_interval_pts'])
        self.assertIn('same_pts_different_hands', w['review_reasons'])

    def test_review_flags_propagated(self):
        t = timeline()
        t['hands'][0]['review_flags'] = ['incompatible_board_progression_requires_review']
        w = build_hand_boundary_review(t)['inter_hand_review_windows'][0]
        self.assertIn('adjacent_hands_have_review_flags', w['review_reasons'])

    def test_bad_hints_rejected(self):
        h = hints()
        h['boundary_hints'][0]['human_confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'Invalid unverified boundary hint'):
            build_hand_boundary_review(timeline(), h)

    def test_no_mutation(self):
        t, h = timeline(), hints()
        original_t, original_h = copy.deepcopy(t), copy.deepcopy(h)
        build_hand_boundary_review(t, h)
        self.assertEqual((t, h), (original_t, original_h))

    def test_file_roundtrip_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'timeline.json', Path(folder)/'boundaries.json'
            t = timeline()
            source.write_text(json.dumps(t), encoding='utf-8')
            result = write_hand_boundary_review(source, output,
                             expected_timeline_sha256=canonical_sha256(t))
            self.assertEqual(json.loads(output.read_text())['counts'], result['counts'])
            with self.assertRaises(ValueError):
                write_hand_boundary_review(source, output)
            with self.assertRaises(ValueError):
                write_hand_boundary_review(source, source)

    def test_invalid_max_gap(self):
        for gap in (-1, 0, float('nan'), float('inf'), True, 3601):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                build_hand_boundary_review(timeline(), max_gap_seconds=gap)

    def test_no_future_board_borrowed_into_boundary(self):
        result = build_hand_boundary_review(timeline())
        w = result['inter_hand_review_windows'][0]
        self.assertNotIn('board', w)
        self.assertNotIn('hero_cards', w)
        self.assertFalse(w['hand_assignment_automated'])


if __name__ == '__main__':
    unittest.main()
