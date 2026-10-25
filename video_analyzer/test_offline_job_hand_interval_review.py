"""Synthetic tests for manual nominal intervals: no verified hand/EV/clip claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_hand_interval_review import (
    template, validate_hand_intervals, review_job, export_review, load_submission)
from test_offline_job_review_windows import observation, timeline


def item(table=1, label='H1', start=0, end=10, confidence=.8):
    return {'table_id': table, 'hand_label': label,
            'start_nominal_seconds': start, 'end_nominal_seconds': end,
            'reviewer_confidence_subjective': confidence,
            'reviewer_notes': 'Manually reviewed sample'}


def make(rows, entries=None):
    source = timeline(rows)
    submission = template(source)
    submission['reviewer'] = 'Reviewer A'
    submission['intervals'] = entries if entries is not None else [item()]
    return source, submission


class ManualIntervalTests(unittest.TestCase):
    def test_blank_template_does_not_infer_hands(self):
        t = template(timeline([observation(1, 0)]))
        self.assertEqual(t['intervals'], [])
        self.assertEqual(len(t['source_windows_sha256']), 64)

    def test_empty_submission_no_hand_claims(self):
        source, submission = make([], [])
        result = validate_hand_intervals(source, submission)
        self.assertEqual(result['counts']['human_marked_intervals'], 0)
        self.assertFalse(result['hand_reconstruction_verified'])
        self.assertFalse(result['ready_for_equity_or_ev'])

    def test_single_table_links_observations(self):
        rows = [observation(1, 0), observation(1, 10, 1, 'confirmed')]
        source, submission = make(rows)
        result = validate_hand_intervals(source, submission)
        self.assertEqual(result['counts']['linked_ocr_observations'], 2)
        self.assertEqual(result['intervals'][0]['observation_count'], 2)
        self.assertFalse(result['intervals'][0]['hand_start_or_end_pts_verified'])

    def test_four_tables_isolated(self):
        rows = [observation(t, 2) for t in range(1, 5)]
        source, submission = make(rows, [item(t, 'H1', 0, 4) for t in range(1, 5)])
        result = validate_hand_intervals(source, submission)
        self.assertEqual(result['counts']['linked_ocr_observations'], 4)
        self.assertEqual([i['table_id'] for i in result['intervals']], [1, 2, 3, 4])

    def test_unassigned_observation_count(self):
        source, submission = make([observation(1, 0), observation(1, 50, 1)])
        self.assertEqual(validate_hand_intervals(source, submission)['counts']['unassigned_ocr_observations'], 1)

    def test_split_one_window_into_two_human_intervals(self):
        source, submission = make([observation(1, 0), observation(1, 10, 1)],
                                  [item(1, 'H1', 0, 2), item(1, 'H2', 8, 11)])
        result = validate_hand_intervals(source, submission)
        self.assertEqual(result['counts']['human_marked_intervals'], 2)
        self.assertEqual(result['counts']['linked_ocr_observations'], 2)

    def test_interval_spanning_two_navigation_windows(self):
        source, submission = make([observation(1, 0), observation(1, 30, 1)],
                                  [item(1, 'H1', 0, 31)])
        result = validate_hand_intervals(source, submission)
        self.assertEqual(len(result['intervals'][0]['source_navigation_window_ids']), 2)

    def test_pending_flag_is_conservative(self):
        source, submission = make([observation(1, 0), observation(1, 10, 1, 'confirmed')])
        self.assertTrue(validate_hand_intervals(source, submission)['intervals'][0]
                        ['linked_window_has_unresolved_observations'])

    def test_stale_window_digest_rejected(self):
        source, submission = make([observation(1, 0)])
        source['observations'].append(observation(1, 5, 1))
        source['counts']['ocr_hints'] = 2
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_hand_intervals(source, submission)

    def test_gap_parameter_changes_digest(self):
        source, submission = make([observation(1, 0), observation(1, 20, 1)])
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_hand_intervals(source, submission, gap_seconds=30)

    def test_reject_injected_authority(self):
        source, submission = make([observation(1, 0)])
        submission['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'structure'):
            validate_hand_intervals(source, submission)

    def test_reject_injected_interval_authority(self):
        source, submission = make([observation(1, 0)])
        submission['intervals'][0]['hand_reconstruction_verified'] = True
        with self.assertRaisesRegex(ValueError, 'structure'):
            validate_hand_intervals(source, submission)

    def test_reject_duplicate_label(self):
        source, submission = make([observation(1, 0), observation(1, 20, 1)],
                                  [item(1, 'H1', 0, 5), item(1, 'H1', 15, 25)])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_hand_intervals(source, submission)

    def test_reject_overlap_and_touch(self):
        source, submission = make([observation(1, 0), observation(1, 10, 1)],
                                  [item(1, 'H1', 0, 5), item(1, 'H2', 5, 12)])
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            validate_hand_intervals(source, submission)

    def test_reject_empty_interval(self):
        source, submission = make([observation(1, 0)], [item(1, 'H1', 5, 10)])
        with self.assertRaisesRegex(ValueError, 'no observed'):
            validate_hand_intervals(source, submission)

    def test_invalid_table(self):
        source, submission = make([observation(1, 0)], [item(5)])
        with self.assertRaisesRegex(ValueError, 'table'):
            validate_hand_intervals(source, submission)

    def test_invalid_numeric_inputs(self):
        for value in (True, -1, float('nan'), float('inf'), 86401):
            with self.subTest(value=value):
                source, submission = make([observation(1, 0)], [item(end=value)])
                with self.assertRaises(ValueError):
                    validate_hand_intervals(source, submission)

    def test_confidence_must_be_subjective_and_bounded(self):
        for value in (True, -0.1, 1.1, float('nan')):
            with self.subTest(value=value):
                source, submission = make([observation(1, 0)], [item(confidence=value)])
                with self.assertRaisesRegex(ValueError, 'confidence'):
                    validate_hand_intervals(source, submission)

    def test_reject_long_interval(self):
        source, submission = make([observation(1, 0)], [item(end=601)])
        with self.assertRaisesRegex(ValueError, 'interval'):
            validate_hand_intervals(source, submission)

    def test_reject_unsafe_label_and_notes(self):
        source, submission = make([observation(1, 0)])
        submission['intervals'][0]['hand_label'] = '../secrets'
        with self.assertRaisesRegex(ValueError, 'label'):
            validate_hand_intervals(source, submission)
        source, submission = make([observation(1, 0)])
        submission['intervals'][0]['reviewer_notes'] = '\x00bad note'
        with self.assertRaisesRegex(ValueError, 'notes'):
            validate_hand_intervals(source, submission)

    def test_reject_duplicate_or_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'submission.json'
            p.write_text('{"job_id":"a", "job_id":"b"}')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_submission(p)
            p.write_text('{"confidence":NaN}')
            with self.assertRaises(ValueError):
                load_submission(p)

    def test_reaudits_timeline_for_job(self):
        source, submission = make([observation(1, 0)])
        with patch('offline_job_hand_interval_review.timeline_job', return_value=source) as audit:
            report = review_job(Mock(), 'a' * 32, '/tmp', submission)
        audit.assert_called_once()
        self.assertEqual(report['counts']['linked_ocr_observations'], 1)

    def test_invalid_job_id_rejected_before_audit(self):
        source, submission = make([observation(1, 0)])
        with patch('offline_job_hand_interval_review.timeline_job') as audit:
            with self.assertRaisesRegex(ValueError, 'job ID'):
                review_job(Mock(), '../x', '/tmp', submission)
            audit.assert_not_called()

    def test_export_exclusive_no_overwrite(self):
        source, submission = make([observation(1, 0)])
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / ('a' * 32)
            folder.mkdir()
            with patch('offline_job_hand_interval_review.timeline_job', return_value=source):
                result = export_review(Mock(), 'a' * 32, root, submission)
                p = folder / 'human_nominal_hand_intervals.json'
                self.assertEqual(json.loads(p.read_text())['counts'], result['counts'])
                with self.assertRaises(FileExistsError):
                    export_review(Mock(), 'a' * 32, root, submission)

    def test_symlink_output_directory_rejected(self):
        source, submission = make([observation(1, 0)])
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'target'
            target.mkdir()
            (Path(root) / ('a' * 32)).symlink_to(target, target_is_directory=True)
            with patch('offline_job_hand_interval_review.timeline_job', return_value=source):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    export_review(Mock(), 'a' * 32, root, submission)

    def test_deterministic_order_and_output(self):
        source, submission = make([observation(2, 10), observation(1, 0)],
                                  [item(2, 'B', 9, 11), item(1, 'A', 0, 1)])
        first = validate_hand_intervals(source, submission)
        second = validate_hand_intervals(source, copy.deepcopy(submission))
        self.assertEqual(first, second)
        self.assertEqual([i['table_id'] for i in first['intervals']], [1, 2])

    def test_integration_with_actual_review_timeline_fixture(self):
        from test_offline_job_review_timeline import TimelineTests
        fixture = TimelineTests('test_four_table_timeline_and_pending')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.build()
        submission = template(source)
        submission['reviewer'] = 'Reviewer A'
        result = validate_hand_intervals(source, submission)
        self.assertEqual(result['counts']['unassigned_ocr_observations'], 4)
        self.assertFalse(result['ready_for_equity_or_ev'])


if __name__ == '__main__':
    unittest.main()
