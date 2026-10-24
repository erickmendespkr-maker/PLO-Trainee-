"""Synthetic-only boundary triage tests: no poker events are certified."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_ocr_boundary_triage import build_ocr_boundary_triage, export_ocr_boundary_triage


def sha(ch):
    return ch * 64


def change(field, old, new, *, table=1, start=1, end=2):
    return {'table_id': table, 'field': field, 'kind': 'possible_visual_value_change',
            'from_decoded_pts_seconds': start, 'at_decoded_pts_seconds': end,
            'from_candidate': old, 'to_candidate': new,
            'source_evidence': [
                {'report_sha256': sha('a'), 'candidate_index': 0, 'roi_sha256': sha('b')},
                {'report_sha256': sha('a'), 'candidate_index': 1, 'roi_sha256': sha('c')}],
            'requires_manual_review': True}


def report(*items):
    return {'schema_version': 1, 'analysis_status': 'unverified_temporal_ocr_review_hints',
            'recording_sha256': sha('d'), 'roi_profile_sha256': sha('e'),
            'source_report_sha256s': [sha('a')], 'review_items': list(items),
            'counts': {'observations': 10, 'review_items': len(items),
                       'possible_changes': sum(x['kind'] == 'possible_visual_value_change' for x in items),
                       'ambiguous_or_uncertain': 0},
            'requires_manual_review': True, 'hand_boundaries_verified': False,
            'cards_or_actions_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False}


A = ['As', 'Kd', 'Qc', 'Jh', 'Ts']
B = ['2s', '3d', '4c', '5h', '6s']


class OCRBoundaryTriageTests(unittest.TestCase):
    def test_private_card_change_is_only_review_window(self):
        result = build_ocr_boundary_triage(report(change('hero_cards', A, B)))
        self.assertEqual(result['counts']['review_windows'], 1)
        self.assertEqual(result['review_windows'][0]['priority'], 'review')
        for key in ('hand_boundaries_verified', 'cards_or_actions_verified',
                    'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                    'strategic_error_established'):
            self.assertIs(result[key], False)

    def test_board_extension_is_not_boundary(self):
        self.assertEqual(build_ocr_boundary_triage(report(change('board', A[:3], A[:4])))
                         ['counts']['review_windows'], 0)

    def test_board_reset_is_candidate(self):
        result = build_ocr_boundary_triage(report(change('board', A, B[:3])))
        self.assertEqual(result['counts']['review_windows'], 1)

    def test_pot_drop_alone_is_not_boundary(self):
        self.assertEqual(build_ocr_boundary_triage(report(change('pot', 20.0, 5.0)))
                         ['counts']['review_windows'], 0)

    def test_pot_drop_corrob_exact_window(self):
        result = build_ocr_boundary_triage(report(change('hero_cards', A, B),
                                                   change('pot', 20.0, 5.0)))
        self.assertEqual(result['review_windows'][0]['priority'], 'review_first')
        self.assertEqual(len(result['review_windows'][0]['signals']), 2)

    def test_different_windows_do_not_corrob(self):
        result = build_ocr_boundary_triage(report(change('hero_cards', A, B),
                                                   change('pot', 20.0, 5.0, start=2, end=3)))
        self.assertEqual(result['review_windows'][0]['priority'], 'review')

    def test_four_tables_isolated(self):
        result = build_ocr_boundary_triage(report(*(change('hero_cards', A, B, table=i)
                                                    for i in range(1, 5))))
        self.assertEqual([x['table_id'] for x in result['review_windows']], [1, 2, 3, 4])

    def test_uncertain_timestamp_downgrades_priority(self):
        uncertain = {'table_id': 1, 'field': 'pot', 'kind': 'decoded_pts_unverified',
                     'at_decoded_pts_seconds': 1.5, 'requires_manual_review': True}
        result = build_ocr_boundary_triage(report(change('hero_cards', A, B),
                                                   change('pot', 20.0, 5.0), uncertain))
        self.assertEqual(result['review_windows'][0]['priority'], 'review')
        self.assertTrue(result['review_windows'][0]['ambiguity_flags'])

    def test_duplicate_field_hints_downgrade_priority(self):
        result = build_ocr_boundary_triage(report(change('hero_cards', A, B),
                                                   change('hero_cards', B, A),
                                                   change('pot', 20.0, 5.0)))
        self.assertEqual(result['review_windows'][0]['priority'], 'review')

    def test_reject_forged_authority(self):
        for field in ('hand_boundaries_verified', 'ready_for_equity_or_ev',
                      'automatic_clip_selection_authorized'):
            with self.subTest(field=field):
                source = report(change('hero_cards', A, B))
                source[field] = True
                with self.assertRaises(ValueError):
                    build_ocr_boundary_triage(source)

    def test_reject_forged_evidence(self):
        source = report(change('hero_cards', A, B))
        source['review_items'][0]['source_evidence'][0]['report_sha256'] = sha('f')
        with self.assertRaises(ValueError):
            build_ocr_boundary_triage(source)

    def test_reject_bad_values_and_timestamps(self):
        for replacement in (float('nan'), True, -1):
            with self.subTest(value=str(replacement)):
                source = report(change('pot', 10.0, 20.0))
                source['review_items'][0]['at_decoded_pts_seconds'] = replacement
                with self.assertRaises(ValueError):
                    build_ocr_boundary_triage(source)
        source = report(change('board', A[:3], A[:4]))
        source['review_items'][0]['to_candidate'] = ['As', 'As', 'Qc', 'Jh']
        with self.assertRaises(ValueError):
            build_ocr_boundary_triage(source)

    def test_reject_unknown_kind_and_wrong_counts(self):
        source = report(change('hero_cards', A, B))
        source['review_items'][0]['kind'] = 'verified_boundary'
        with self.assertRaises(ValueError):
            build_ocr_boundary_triage(source)
        source = report(change('hero_cards', A, B))
        source['counts']['review_items'] = 0
        with self.assertRaises(ValueError):
            build_ocr_boundary_triage(source)

    def test_budget(self):
        source = report(change('hero_cards', A, B),
                        change('hero_cards', A, B, start=3, end=4))
        with self.assertRaises(ValueError):
            build_ocr_boundary_triage(source, max_windows=1)

    def test_export_cli_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            source, output = folder / 'temporal.json', folder / 'boundary.json'
            source.write_text(json.dumps(report(change('hero_cards', A, B))))
            proc = subprocess.run([sys.executable, str(Path(__file__).with_name('activity_ocr_boundary_triage.py')),
                                   str(source), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(output.read_text())
            self.assertEqual(result['source_temporal_report_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            with self.assertRaises((ValueError, FileExistsError)):
                export_ocr_boundary_triage(source, output)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            original, link = folder / 'original.json', folder / 'link.json'
            original.write_text(json.dumps(report()))
            link.symlink_to(original)
            with self.assertRaises(ValueError):
                export_ocr_boundary_triage(link, folder / 'out.json')


if __name__ == '__main__':
    unittest.main()
