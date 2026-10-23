"""Synthetic regression tests: reviewed activity OCR never becomes automatic EV."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from activity_snapshot_chain import (build_activity_snapshot_queue, canonical_sha256,
                                     run_activity_snapshot_queue)
from hand_history import Observation

PTS = 'decoded_filtergraph_pts_not_capture_time'


def fixture(tables=(1, 2, 3, 4)):
    observations, provenance = [], []
    def add(table, t, action, *, pot=None, board=None, hero_cards=None):
        obs = Observation(table, t, action, .96, f'h{table}',
                          actor='hero' if action == 'call' else None,
                          variant='PLO5', pot=pot, board=board, hero_cards=hero_cards,
                          field_confidence={field: .91 for field, value in
                            [('pot', pot), ('board', board), ('hero_cards', hero_cards)] if value is not None})
        idx = len(observations)
        observations.append(asdict(obs))
        evidence = []
        for field, value in [('pot', pot), ('board', board), ('hero_cards', hero_cards)]:
            if value is None:
                continue
            evidence.append({'field': field, 'candidate_index': idx * 10 + len(evidence),
                             'source_timestamp': t, 'source_image': f'table{table}/f{idx}.png',
                             'source_timestamp_semantics': PTS,
                             'approved_value': list(value) if isinstance(value, tuple) else value,
                             'reviewer_confidence': .91})
        provenance.append({'event_index': idx, 'table_id': table, 'timestamp': t,
                           'hand_id': f'h{table}', 'human_confirmed': True,
                           'evidence': evidence})
    for table in tables:
        add(table, 0, 'hand_start', pot=20 + table,
            hero_cards=('As', 'Ks', '2d', '3c', '4h'))
    for table in tables:
        add(table, 1, 'board', board=('Qs', 'Js', 'Ts'))
    for table in tables:
        add(table, 2, 'call')
    for table in tables:
        add(table, 3, 'hand_end')
    return {'schema_version': 1, 'analysis_status': 'human_reviewed_activity_observations',
            'ready_for_equity_or_ev': False, 'timestamp_semantics': PTS,
            'recording_sha256': 'a' * 64, 'evidence_manifest_sha256': 'b' * 64,
            'ocr_report_sha256': 'c' * 64,
            'observations': observations, 'provenance': provenance}


class ActivitySnapshotChainTests(unittest.TestCase):
    def test_four_tables_prior_only_and_evidence_bound(self):
        report = build_activity_snapshot_queue(fixture())
        self.assertEqual(report['counts']['decisions'], 4)
        self.assertEqual([t['table_id'] for t in report['tasks']], [1, 2, 3, 4])
        for t in report['tasks']:
            self.assertFalse(t['ready_for_ev'])
            self.assertFalse(t['human_confirmed'])
            self.assertEqual(t['reviewed_ocr_sources']['pot']['source_timestamp'], 0)
            self.assertEqual(t['reviewed_ocr_sources']['board']['source_timestamp'], 1)
            self.assertEqual(t['visible_hints_unverified']['pot']['value'], 20+t['table_id'])
            self.assertEqual(t['action_source']['source_type'], 'human_annotated_action_not_ocr_verified')
            self.assertIn('opponent_range_requires_manual_input', t['blockers'])
        self.assertFalse(report['ready_for_equity_or_ev'])

    def test_pin_exact_report_digest(self):
        report = fixture((1,))
        digest = canonical_sha256(report)
        self.assertEqual(build_activity_snapshot_queue(report,
                         expected_review_sha256=digest)['source_review_sha256'], digest)
        altered = copy.deepcopy(report)
        altered['observations'][0]['notes'] = 'modified'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_activity_snapshot_queue(altered, expected_review_sha256=digest)

    def test_reject_not_reviewed_or_ev_ready(self):
        for key, value in [('analysis_status', 'unverified_ocr_candidates_only'),
                           ('ready_for_equity_or_ev', True)]:
            report = fixture((1,)); report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_activity_snapshot_queue(report)

    def test_reject_missing_and_bad_hashes(self):
        for key in ('recording_sha256', 'evidence_manifest_sha256', 'ocr_report_sha256'):
            report = fixture((1,)); report[key] = 'not_sha'
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_activity_snapshot_queue(report)

    def test_reject_requested_seek_semantics(self):
        report = fixture((1,)); report['timestamp_semantics'] = 'requested_seek_not_decoded'
        report['timestamp_semantics'] = 'requested_seek_seconds'
        with self.assertRaisesRegex(ValueError, 'Decoded PTS'):
            build_activity_snapshot_queue(report)

    def test_reject_changed_table(self):
        report = fixture((1,)); report['provenance'][0]['table_id'] = 2
        with self.assertRaisesRegex(ValueError, 'identity'):
            build_activity_snapshot_queue(report)

    def test_reject_changed_hand(self):
        report = fixture((1,)); report['provenance'][0]['hand_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'identity'):
            build_activity_snapshot_queue(report)

    def test_reject_changed_observation_timestamp(self):
        report = fixture((1,)); report['observations'][1]['timestamp'] = 1.25
        with self.assertRaisesRegex(ValueError, 'identity'):
            build_activity_snapshot_queue(report)

    def test_reject_future_source_pts(self):
        report = fixture((1,)); report['provenance'][0]['evidence'][0]['source_timestamp'] = 3
        with self.assertRaisesRegex(ValueError, 'decoded timestamp'):
            build_activity_snapshot_queue(report)

    def test_reject_modified_approved_value(self):
        report = fixture((1,)); report['provenance'][0]['evidence'][0]['approved_value'] = 999
        with self.assertRaisesRegex(ValueError, 'differs'):
            build_activity_snapshot_queue(report)

    def test_reject_observation_field_without_evidence(self):
        report = fixture((1,)); report['provenance'][0]['evidence'].pop()
        with self.assertRaisesRegex(ValueError, 'lacks exact'):
            build_activity_snapshot_queue(report)

    def test_reject_extra_unbacked_observation_field(self):
        report = fixture((1,)); report['observations'][2]['pot'] = 500
        with self.assertRaisesRegex(ValueError, 'lacks exact'):
            build_activity_snapshot_queue(report)

    def test_reject_duplicate_candidate_index(self):
        report = fixture((1,)); ev = report['provenance'][1]['evidence'][0]
        ev['candidate_index'] = report['provenance'][0]['evidence'][0]['candidate_index']
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_activity_snapshot_queue(report)

    def test_reject_changed_reviewer_confidence(self):
        report = fixture((1,)); report['provenance'][0]['evidence'][0]['reviewer_confidence'] = .2
        with self.assertRaisesRegex(ValueError, 'confidence mismatch'):
            build_activity_snapshot_queue(report)

    def test_reject_unsafe_path(self):
        for path in ('../other.png', '/etc/passwd', 'a\\b.png', ''):
            report = fixture((1,)); report['provenance'][0]['evidence'][0]['source_image'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_activity_snapshot_queue(report)

    def test_reject_missing_approval(self):
        report = fixture((1,)); report['provenance'][0]['human_confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'identity'):
            build_activity_snapshot_queue(report)

    def test_same_frame_is_not_prior(self):
        report = fixture((1,))
        report['observations'][1]['timestamp'] = 2
        report['provenance'][1]['timestamp'] = 2
        report['provenance'][1]['evidence'][0]['source_timestamp'] = 2
        task = build_activity_snapshot_queue(report)['tasks'][0]
        self.assertIsNone(task['visible_hints_unverified']['board'])
        self.assertIsNone(task['reviewed_ocr_sources']['board'])

    def test_stale_fields_still_block_ev(self):
        report = fixture((1,))
        task = build_activity_snapshot_queue(report, max_age_seconds=.5)['tasks'][0]
        self.assertIn('pot_stale_observation', task['blockers'])
        self.assertFalse(task['ready_for_ev'])

    def test_reject_out_of_order_observations(self):
        report = fixture((1,))
        report['observations'][1]['timestamp'] = -1
        with self.assertRaises(ValueError):
            build_activity_snapshot_queue(report)

    def test_file_roundtrip_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root/'reviewed.json', root/'queue.json'
            report = fixture((1,))
            source.write_text(json.dumps(report))
            result = run_activity_snapshot_queue(source, output,
                        expected_review_sha256=canonical_sha256(report))
            self.assertEqual(json.loads(output.read_text())['source_review_sha256'],
                             result['source_review_sha256'])
            with self.assertRaises(ValueError):
                run_activity_snapshot_queue(source, output)
            with self.assertRaises(ValueError):
                run_activity_snapshot_queue(source, source)


if __name__ == '__main__':
    unittest.main()
