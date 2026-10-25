"""Synthetic tests for fail-closed nominal hand reconstruction checklists."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline_job_hand_reconstruction_checklist import (
    build_checklist, export_checklist, validate_dossiers,
)
from offline_job_hand_evidence_dossier import build_dossiers
from test_offline_job_hand_evidence_dossier import row, entry, make


def report(rows=None, spans=None):
    source, submission = make([row()] if rows is None else rows, spans)
    return build_dossiers(source, submission)


class ChecklistTests(unittest.TestCase):
    def test_one_hand_stays_blocked(self):
        result = build_checklist(report())
        self.assertEqual(result['counts']['hands_to_review'], 1)
        self.assertEqual(result['counts']['math_ready'], 0)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])

    def test_empty_intervals_remain_empty(self):
        result = build_checklist(report([row()], []))
        self.assertEqual(result['tasks'], [])
        self.assertEqual(result['counts']['hands_to_review'], 0)

    def test_all_four_fields_missing_approved(self):
        result = build_checklist(report())
        self.assertEqual(result['tasks'][0]['missing_approved_fields'],
                         ['hero_cards', 'board', 'pot', 'bet'])

    def test_approved_field_still_not_math_fact(self):
        result = build_checklist(report([row(status='confirmed', field='pot')]))
        self.assertNotIn('pot', result['tasks'][0]['missing_approved_fields'])
        self.assertFalse(result['tasks'][0]['ready_for_equity_or_ev'])
        self.assertTrue(all(x is None for x in
                            result['tasks'][0]['manual_reconstruction_template'].values()))

    def test_uncertain_and_rejected_are_unresolved(self):
        result = build_checklist(report([row(1, 0, 0, 'uncertain', 'pot'),
                                         row(1, 0, 1, 'rejected', 'bet')]))
        self.assertEqual(result['tasks'][0]['unresolved_fields'], ['pot', 'bet'])

    def test_conflict_same_stamp_is_flagged(self):
        result = build_checklist(report([row(1, 0, 0, 'confirmed', 'pot', '100'),
                                         row(1, 0, 1, 'corrected', 'pot', '125')]))
        self.assertEqual(result['tasks'][0]['same_timestamp_conflict_fields'], ['pot'])

    def test_temporal_change_is_not_conflict(self):
        result = build_checklist(report([row(1, 0, 0, 'confirmed', 'pot', '100'),
                                         row(1, 5, 1, 'corrected', 'pot', '125')]))
        self.assertEqual(result['tasks'][0]['same_timestamp_conflict_fields'], [])
        self.assertEqual(result['tasks'][0]['temporally_changing_fields'], ['pot'])

    def test_four_tables_do_not_mix(self):
        r = report([row(t, 0, t, 'confirmed', 'pot', str(t)) for t in range(1, 5)],
                   [entry(t, 'H1', 0, 2) for t in range(1, 5)])
        result = build_checklist(r)
        self.assertEqual([x['table_id'] for x in result['tasks']], [1, 2, 3, 4])
        self.assertEqual(result['counts']['hands_to_review'], 4)

    def test_source_digest_deterministic(self):
        r = report()
        self.assertEqual(build_checklist(r), build_checklist(copy.deepcopy(r)))

    def test_reject_promoted_global_math_gate(self):
        r = report()
        r['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'authority'):
            build_checklist(r)

    def test_reject_promoted_hand_gate(self):
        r = report()
        r['dossiers'][0]['hand_reconstruction_verified'] = True
        with self.assertRaisesRegex(ValueError, 'authority'):
            build_checklist(r)

    def test_reject_populated_manual_worksheet(self):
        r = report()
        r['dossiers'][0]['manual_reconstruction_worksheet']['hero_cards'] = ['As']
        with self.assertRaisesRegex(ValueError, 'already populated'):
            build_checklist(r)

    def test_reject_cross_table_evidence(self):
        r = report()
        r['dossiers'][0]['observations'][0]['table_id'] = 2
        with self.assertRaisesRegex(ValueError, 'Cross-table'):
            build_checklist(r)

    def test_reject_timestamp_outside_interval(self):
        r = report()
        r['dossiers'][0]['observations'][0]['nominal_timestamp_seconds'] = 1000
        with self.assertRaisesRegex(ValueError, 'outside'):
            build_checklist(r)

    def test_reject_tampered_review_count(self):
        r = report()
        r['dossiers'][0]['field_summaries']['pot']['review_status_counts']['pending'] = 10
        with self.assertRaisesRegex(ValueError, 'counts'):
            build_checklist(r)

    def test_reject_tampered_conflict_flags(self):
        r = report()
        r['dossiers'][0]['field_summaries']['pot']['same_nominal_timestamp_conflicts'] = [0]
        with self.assertRaisesRegex(ValueError, 'conflict'):
            build_checklist(r)

    def test_reject_promoted_unapproved_value(self):
        r = report()
        r['dossiers'][0]['observations'][0]['human_annotation_value_unparsed'] = 'fake'
        with self.assertRaisesRegex(ValueError, 'Unapproved'):
            build_checklist(r)

    def test_reject_duplicate_evidence(self):
        r = report()
        duplicate = copy.deepcopy(r['dossiers'][0]['observations'][0])
        r['dossiers'][0]['observations'].append(duplicate)
        s = r['dossiers'][0]['field_summaries']['pot']
        s['observation_count'] += 1
        s['review_status_counts']['pending'] += 1
        r['counts']['linked_ocr_observations'] += 1
        with self.assertRaisesRegex(ValueError, 'Duplicate evidence'):
            build_checklist(r)

    def test_reject_invalid_digest(self):
        r = report()
        r['source_sha256'] = 'not-a-hash'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            build_checklist(r)

    def test_reject_nan_timestamp(self):
        r = report()
        r['dossiers'][0]['start_nominal_seconds_human_marked'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'interval'):
            build_checklist(r)

    def test_reject_wrong_count(self):
        r = report()
        r['counts']['linked_ocr_observations'] += 1
        with self.assertRaisesRegex(ValueError, 'totals'):
            build_checklist(r)

    def test_reject_bool_count(self):
        r = report()
        r['counts']['math_ready'] = False
        with self.assertRaisesRegex(ValueError, 'counts'):
            build_checklist(r)

    def test_export_and_prevent_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = Path(directory) / 'dossiers.json', Path(directory) / 'checklist.json'
            src.write_text(json.dumps(report()), encoding='utf-8')
            result = export_checklist(src, dst)
            self.assertEqual(json.loads(dst.read_text())['counts'], result['counts'])
            with self.assertRaises(FileExistsError):
                export_checklist(src, dst)

    def test_export_rejects_input_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            real, link, dst = (Path(directory) / p for p in ('real', 'link', 'out'))
            real.write_text(json.dumps(report()))
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                export_checklist(link, dst)

    def test_export_rejects_output_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            src, real, link = (Path(directory) / p for p in ('src', 'real', 'link'))
            src.write_text(json.dumps(report()))
            real.write_text('keep')
            link.symlink_to(real)
            with self.assertRaises(FileExistsError):
                export_checklist(src, link)
            self.assertEqual(real.read_text(), 'keep')

    def test_export_rejects_nonstandard_json(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = Path(directory) / 'src', Path(directory) / 'dst'
            src.write_text('{"value":NaN}')
            with self.assertRaises(ValueError):
                export_checklist(src, dst)

    def test_source_mutation_during_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = Path(directory) / 'src', Path(directory) / 'dst'
            src.write_text(json.dumps(report()))
            original = build_checklist
            def changed(value):
                src.write_text('{}')
                return original(value)
            with patch('offline_job_hand_reconstruction_checklist.build_checklist', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    export_checklist(src, dst)
            self.assertFalse(dst.exists())


if __name__ == '__main__':
    unittest.main()
