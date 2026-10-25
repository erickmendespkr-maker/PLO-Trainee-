"""Deterministic tests: OCR windows are never verified poker hands."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_review_windows import build_windows, windows_job, export_windows


def observation(table, stamp, candidate=0, status='pending', field='pot'):
    approved = status in ('confirmed', 'corrected')
    return {
        'table_id': table, 'nominal_timestamp_seconds': stamp,
        'field': field, 'candidate_index': candidate,
        'source_image': f'table_0{table}/frame_{candidate:05d}.png',
        'source_image_sha256': f'{table}' * 64,
        'review_status': status,
        'human_annotation_value': '100' if approved else None,
        'human_confidence_subjective': .8 if approved else None,
        'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
    }


def timeline(rows):
    return {
        'schema_version': 1, 'analysis_status': 'human_reviewed_ocr_timeline_unverified_no_math',
        'job_id': 'a' * 32, 'source_sha256': 'b' * 64,
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'requires_manual_hand_reconstruction': True,
        'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'counts': {'ocr_hints': len(rows)}, 'observations': rows,
    }


class WindowTests(unittest.TestCase):
    def test_empty(self):
        result = build_windows(timeline([]))
        self.assertEqual(result['window_count'], 0)
        self.assertFalse(result['ready_for_equity_or_ev'])

    def test_four_tables_are_separate(self):
        result = build_windows(timeline([observation(t, 0) for t in range(1, 5)]))
        self.assertEqual([w['table_id'] for w in result['windows']], [1, 2, 3, 4])
        self.assertTrue(all(w['hand_start_or_end_verified'] is False for w in result['windows']))

    def test_sort_and_group_same_table(self):
        rows = [observation(1, 12, 2), observation(1, 0, 0), observation(1, 7, 1)]
        result = build_windows(timeline(rows))
        self.assertEqual(result['window_count'], 1)
        self.assertEqual(result['windows'][0]['observation_count'], 3)
        self.assertEqual(result['windows'][0]['first_nominal_timestamp_seconds'], 0)
        self.assertEqual(result['windows'][0]['last_nominal_timestamp_seconds'], 12)

    def test_gap_splits_without_claiming_hand_boundary(self):
        result = build_windows(timeline([observation(2, 0), observation(2, 16, 1)]))
        self.assertEqual(result['window_count'], 2)
        self.assertFalse(result['windows'][1]['hand_start_or_end_verified'])

    def test_gap_equal_threshold_keeps_group(self):
        result = build_windows(timeline([observation(2, 0), observation(2, 15, 1)]))
        self.assertEqual(result['window_count'], 1)

    def test_span_splits_even_with_small_gaps(self):
        rows = [observation(1, t, i) for i, t in enumerate(range(0, 136, 15))]
        result = build_windows(timeline(rows))
        self.assertEqual(result['window_count'], 2)

    def test_pending_and_uncertain_mark_unresolved(self):
        rows = [observation(1, 0, 0, 'confirmed'), observation(1, 1, 1, 'uncertain')]
        w = build_windows(timeline(rows))['windows'][0]
        self.assertTrue(w['has_unresolved_observations'])
        self.assertEqual(w['status_counts']['confirmed'], 1)
        self.assertEqual(w['status_counts']['uncertain'], 1)

    def test_fully_confirmed_still_blocks_math(self):
        w = build_windows(timeline([observation(1, 0, 0, 'confirmed')]))
        self.assertFalse(w['ready_for_equity_or_ev'])
        self.assertFalse(w['automatic_clip_selection_authorized'])

    def test_duplicate_observation_rejected(self):
        row = observation(1, 0)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_windows(timeline([row, copy.deepcopy(row)]))

    def test_bad_table_and_image_mismatch_rejected(self):
        row = observation(1, 0)
        row['source_image'] = 'table_02/frame_00000.png'
        with self.assertRaisesRegex(ValueError, 'image'):
            build_windows(timeline([row]))
        row = observation(5, 0)
        with self.assertRaisesRegex(ValueError, 'table'):
            build_windows(timeline([row]))

    def test_path_traversal_rejected(self):
        row = observation(1, 0)
        row['source_image'] = '../../secrets.png'
        with self.assertRaises(ValueError):
            build_windows(timeline([row]))

    def test_nan_inf_bool_and_negative_timestamps_rejected(self):
        for stamp in (float('nan'), float('inf'), True, -1, 86401):
            with self.subTest(stamp=stamp):
                with self.assertRaisesRegex(ValueError, 'timestamp'):
                    build_windows(timeline([observation(1, stamp)]))

    def test_bad_parameters_rejected(self):
        for gap, span in [(0, 120), (121, 121), (20, 19), (15, 601), (True, 120), (float('nan'), 120)]:
            with self.subTest(gap=gap, span=span):
                with self.assertRaises(ValueError):
                    build_windows(timeline([]), gap_seconds=gap, max_span_seconds=span)

    def test_math_flags_fail_closed(self):
        for flag in ('ready_for_equity_or_ev', 'hand_reconstruction_verified', 'automatic_clip_selection_authorized'):
            t = timeline([])
            t[flag] = True
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(ValueError, 'prohibited'):
                    build_windows(t)

    def test_approved_value_missing_or_pending_value_rejected(self):
        row = observation(1, 0, 0, 'confirmed')
        row['human_annotation_value'] = None
        with self.assertRaisesRegex(ValueError, 'annotation'):
            build_windows(timeline([row]))
        row = observation(1, 0)
        row['human_annotation_value'] = 'fake'
        with self.assertRaisesRegex(ValueError, 'annotation'):
            build_windows(timeline([row]))

    def test_invalid_counts_rejected(self):
        t = timeline([observation(1, 0)])
        t['counts']['ocr_hints'] = 99
        with self.assertRaisesRegex(ValueError, 'count'):
            build_windows(t)

    def test_deterministic_order_and_digest(self):
        rows = [observation(2, 20), observation(1, 10), observation(2, 0, 1)]
        a = build_windows(timeline(rows))
        b = build_windows(timeline(rows))
        self.assertEqual(a, b)
        self.assertEqual(len(a['source_timeline_sha256']), 64)

    def test_limit(self):
        t = timeline([observation(1, 0)] * 20001)
        with self.assertRaisesRegex(ValueError, 'count'):
            build_windows(t)

    def test_reaudits_before_building(self):
        with patch('offline_job_review_windows.timeline_job', return_value=timeline([])) as audited:
            result = windows_job(Mock(), 'a' * 32, '/tmp')
        self.assertEqual(result['window_count'], 0)
        audited.assert_called_once()

    def test_export_write_once_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / ('a' * 32)
            folder.mkdir()
            with patch('offline_job_review_windows.timeline_job', return_value=timeline([observation(1, 0)])):
                result = export_windows(Mock(), 'a' * 32, root)
                self.assertEqual(result['window_count'], 1)
                output = folder / 'human_ocr_review_windows.json'
                self.assertEqual(json.loads(output.read_text())['window_count'], 1)
                with self.assertRaises(FileExistsError):
                    export_windows(Mock(), 'a' * 32, root)

    def test_symlink_output_directory_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'target'
            target.mkdir()
            (Path(root) / ('a' * 32)).symlink_to(target, target_is_directory=True)
            with patch('offline_job_review_windows.timeline_job', return_value=timeline([])):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    export_windows(Mock(), 'a' * 32, root)

    def test_invalid_job_id_rejected_before_audit(self):
        with patch('offline_job_review_windows.timeline_job') as audited:
            with self.assertRaisesRegex(ValueError, 'job ID'):
                windows_job(Mock(), '../bad', '/tmp')
            audited.assert_not_called()

    def test_integration_from_real_timeline_fixture(self):
        from test_offline_job_review_timeline import TimelineTests
        fixture = TimelineTests('test_four_table_timeline_and_pending')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.build()
        result = build_windows(source)
        self.assertEqual(result['window_count'], 4)
        self.assertEqual(result['observation_count'], 4)
        self.assertTrue(result['requires_manual_hand_reconstruction'])


    def test_real_video_fixture_reaudited_and_tamper_blocked(self):
        from test_offline_job_review_handoff import HandoffTests
        from offline_job_review_decisions import validate_submission, handoff_sha256
        fixture = HandoffTests('test_unapproved_ocr_linked')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.ocr(text='120', field='pot')
        handoff = fixture.build()
        sub = {'schema_version': 1, 'job_id': fixture.job_id,
               'handoff_sha256': handoff_sha256(handoff), 'reviewer': 'reviewer',
               'decisions': [{'table_id': 1, 'nominal_timestamp_seconds': 0.0,
                              'field': 'pot', 'candidate_index': 0,
                              'status': 'confirmed', 'value': '120',
                              'confidence': .8, 'reason': 'Conferido'}]}
        report = validate_submission(handoff, sub)
        (fixture.folder / 'human_ocr_review.json').write_text(json.dumps(report), encoding='utf-8')
        result = windows_job(fixture.store, fixture.job_id, fixture.root / 'results')
        self.assertEqual(result['window_count'], 1)
        self.assertFalse(result['ready_for_equity_or_ev'])
        fixture.image.write_bytes(fixture.image.read_bytes() + b'tampered')
        with self.assertRaises(ValueError):
            windows_job(fixture.store, fixture.job_id, fixture.root / 'results')


if __name__ == '__main__':
    unittest.main()
