"""Synthetic, fail-closed tests for nominal per-hand evidence dossiers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_hand_evidence_dossier import build_dossiers, dossiers_job, export_dossiers
from offline_job_hand_interval_review import template
from test_offline_job_review_windows import observation, timeline


def row(table=1, stamp=0, candidate=0, status='pending', field='pot', value='100'):
    result = observation(table, stamp, candidate, status, field)
    result.update(original_ocr_text_unverified='OCR:' + field,
                  review_reason='Synthetic human review' if status != 'pending' else None,
                  reviewer='Reviewer A' if status != 'pending' else None)
    if status in ('confirmed', 'corrected'):
        result['human_annotation_value'] = value
    return result


def entry(table=1, label='H1', start=0, end=10):
    return {'table_id': table, 'hand_label': label,
            'start_nominal_seconds': start, 'end_nominal_seconds': end,
            'reviewer_confidence_subjective': .75,
            'reviewer_notes': 'Reviewed synthetic interval'}


def make(rows, spans=None):
    source = timeline(rows)
    submission = template(source)
    submission['reviewer'] = 'Reviewer A'
    submission['intervals'] = [entry()] if spans is None else spans
    return source, submission


class DossierTests(unittest.TestCase):
    def test_empty_intervals_are_not_inferred(self):
        source, submission = make([row()], [])
        result = build_dossiers(source, submission)
        self.assertEqual(result['counts']['dossiers'], 0)
        self.assertEqual(result['counts']['unassigned_ocr_observations'], 1)
        self.assertFalse(result['ready_for_equity_or_ev'])

    def test_one_interval_preserves_original_and_human_value(self):
        source, submission = make([row(status='corrected', value='125')])
        result = build_dossiers(source, submission)
        item = result['dossiers'][0]['observations'][0]
        self.assertEqual(item['original_ocr_text_unverified'], 'OCR:pot')
        self.assertEqual(item['human_annotation_value_unparsed'], '125')
        self.assertEqual(item['source_image_sha256'], '1' * 64)
        self.assertEqual(item['human_confidence_subjective'], .8)
        self.assertFalse(result['dossiers'][0]['ready_for_equity_or_ev'])

    def test_no_ocr_values_promoted_to_manual_reconstruction(self):
        source, submission = make([row(status='confirmed', field='hero_cards')])
        draft = build_dossiers(source, submission)['dossiers'][0]['manual_reconstruction_worksheet']
        self.assertTrue(all(value is None for value in draft.values()))

    def test_four_tables_isolated(self):
        source, submission = make([row(t, 0, t) for t in range(1, 5)],
                                  [entry(t, 'H1', 0, 2) for t in range(1, 5)])
        result = build_dossiers(source, submission)
        self.assertEqual([d['table_id'] for d in result['dossiers']], [1, 2, 3, 4])
        self.assertEqual(result['counts']['linked_ocr_observations'], 4)

    def test_unassigned_observations_not_lost(self):
        source, submission = make([row(), row(1, 60, 1)])
        self.assertEqual(build_dossiers(source, submission)['counts']['unassigned_ocr_observations'], 1)

    def test_multiple_intervals_one_window(self):
        source, submission = make([row(1, 0), row(1, 10, 1)],
                                  [entry(1, 'A', 0, 2), entry(1, 'B', 8, 12)])
        result = build_dossiers(source, submission)
        self.assertEqual([len(d['observations']) for d in result['dossiers']], [1, 1])

    def test_interval_crosses_navigation_windows(self):
        source, submission = make([row(1, 0), row(1, 30, 1)], [entry(1, 'A', 0, 31)])
        self.assertEqual(len(build_dossiers(source, submission)['dossiers'][0]['source_navigation_window_ids']), 2)

    def test_pending_uncertain_rejected_remain_unresolved(self):
        source, submission = make([row(1, 0, 0, 'pending'), row(1, 1, 1, 'uncertain'),
                                   row(1, 2, 2, 'rejected')])
        result = build_dossiers(source, submission)
        d = result['dossiers'][0]
        self.assertIn('unresolved_ocr_observations', d['quality_flags'])
        self.assertEqual(d['field_summaries']['pot']['human_approved_observation_count'], 0)

    def test_confirmed_does_not_authorize_math(self):
        source, submission = make([row(1, 0, 0, 'confirmed')])
        result = build_dossiers(source, submission)
        self.assertEqual(result['counts']['math_ready'], 0)
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['dossiers'][0]['field_summaries']['pot']['usable_as_mathematical_fact'])

    def test_missing_fields_are_explicit(self):
        source, submission = make([row(status='confirmed')])
        d = build_dossiers(source, submission)['dossiers'][0]
        self.assertTrue(d['field_summaries']['hero_cards']['missing_from_interval'])
        self.assertIn('missing_ocr_field_observations', d['quality_flags'])

    def test_temporal_changes_are_not_called_same_timestamp_conflict(self):
        source, submission = make([row(1, 0, 0, 'confirmed', 'pot', '100'),
                                   row(1, 5, 1, 'corrected', 'pot', '200')])
        d = build_dossiers(source, submission)['dossiers'][0]
        self.assertEqual(d['field_summaries']['pot']['same_nominal_timestamp_conflicts'], [])
        self.assertIn('temporal_value_changes_require_action_sequence_review', d['quality_flags'])
        self.assertNotIn('different_human_values_same_field_and_nominal_timestamp', d['quality_flags'])

    def test_simultaneous_different_values_flagged(self):
        source, submission = make([row(1, 0, 0, 'confirmed', 'pot', '100'),
                                   row(1, 0, 1, 'corrected', 'pot', '200')])
        d = build_dossiers(source, submission)['dossiers'][0]
        self.assertEqual(d['field_summaries']['pot']['same_nominal_timestamp_conflicts'], [0.0])
        self.assertIn('different_human_values_same_field_and_nominal_timestamp', d['quality_flags'])

    def test_deterministic_with_shuffled_input(self):
        rows = [row(1, 5, 1), row(1, 0, 0), row(2, 0, 2)]
        source, submission = make(rows, [entry(1, 'A', 0, 10), entry(2, 'B', 0, 10)])
        first = build_dossiers(source, submission)
        source['observations'].reverse()
        # Window digest intentionally binds to the source timeline order.
        refreshed = template(source)
        refreshed['reviewer'] = submission['reviewer']
        refreshed['intervals'] = copy.deepcopy(submission['intervals'])
        second = build_dossiers(source, refreshed)
        self.assertEqual(first['dossiers'], second['dossiers'])
        self.assertNotEqual(first['source_timeline_sha256'], second['source_timeline_sha256'])

    def test_stale_submission_rejected(self):
        source, submission = make([row()])
        source['observations'].append(row(1, 2, 1))
        source['counts']['ocr_hints'] = 2
        with self.assertRaisesRegex(ValueError, 'digest'):
            build_dossiers(source, submission)

    def test_gap_parameter_binding(self):
        source, submission = make([row(1, 0), row(1, 20, 1)])
        with self.assertRaisesRegex(ValueError, 'digest'):
            build_dossiers(source, submission, gap_seconds=30)

    def test_bad_field_rejected(self):
        source, submission = make([row(field='password')])
        with self.assertRaisesRegex(ValueError, 'field'):
            build_dossiers(source, submission)

    def test_duplicate_candidate_rejected(self):
        r = row()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            make([r, copy.deepcopy(r)])

    def test_tampered_authority_rejected(self):
        source, submission = make([row()])
        source['observations'][0]['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'authorizes'):
            build_dossiers(source, submission)

    def test_overlapping_intervals_rejected(self):
        source, submission = make([row(), row(1, 5, 1)],
                                  [entry(1, 'A', 0, 4), entry(1, 'B', 4, 8)])
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            build_dossiers(source, submission)

    def test_reaudit_called(self):
        source, submission = make([row()])
        with patch('offline_job_hand_evidence_dossier.timeline_job', return_value=source) as audit:
            result = dossiers_job(Mock(), 'a' * 32, '/tmp', submission)
        audit.assert_called_once()
        self.assertEqual(result['counts']['dossiers'], 1)

    def test_bad_job_id_rejected_before_audit(self):
        source, submission = make([row()])
        with patch('offline_job_hand_evidence_dossier.timeline_job') as audit:
            with self.assertRaisesRegex(ValueError, 'job ID'):
                dossiers_job(Mock(), '../bad', '/tmp', submission)
            audit.assert_not_called()

    def test_export_exclusive_no_overwrite(self):
        source, submission = make([row()])
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / ('a' * 32)
            folder.mkdir()
            with patch('offline_job_hand_evidence_dossier.timeline_job', return_value=source):
                result = export_dossiers(Mock(), 'a' * 32, root, submission)
                saved = json.loads((folder / 'human_hand_evidence_dossiers.json').read_text())
                self.assertEqual(saved['counts'], result['counts'])
                with self.assertRaises(FileExistsError):
                    export_dossiers(Mock(), 'a' * 32, root, submission)

    def test_symlink_directory_rejected(self):
        source, submission = make([row()])
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / 'real'
            folder.mkdir()
            (Path(root) / ('a' * 32)).symlink_to(folder, target_is_directory=True)
            with patch('offline_job_hand_evidence_dossier.timeline_job', return_value=source):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    export_dossiers(Mock(), 'a' * 32, root, submission)

    def test_integrates_with_actual_timeline_fixture(self):
        from test_offline_job_review_timeline import TimelineTests
        fixture = TimelineTests('test_four_table_timeline_and_pending')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.build()
        submission = template(source)
        submission['reviewer'] = 'Reviewer A'
        submission['intervals'] = [entry(t, 'H1', t-1, t) for t in range(1, 5)]
        result = build_dossiers(source, submission)
        self.assertEqual(result['counts']['dossiers'], 4)
        self.assertFalse(result['ready_for_equity_or_ev'])


if __name__ == '__main__':
    unittest.main()
