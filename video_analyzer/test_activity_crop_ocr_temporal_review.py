"""Synthetic-only checks for unverified temporal OCR review hints."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_crop_ocr_temporal_review import build_temporal_ocr_review, export_temporal_ocr_review


def sha(ch):
    return ch * 64


def candidate(t, text='Pot: 10.00', table=1, field='pot', confidence=0.92,
              verified=True, roi=None):
    parsed = float(text.split(':')[-1]) if field in ('pot', 'bet') and ':' in text else None
    if field in ('board', 'hero_cards'):
        parsed = text.split(' ') if text else None
    return {'table_id': table, 'timestamp': t, 'requested_seek_pts_seconds': t,
            'decoded_frame_pts_seconds': t if verified else None,
            'decoded_pts_verified_by_identical_png': verified,
            'field': field, 'raw_text': text, 'parsed_candidate': parsed,
            'mean_engine_confidence': confidence,
            'roi_coordinates_in_table_crop': roi or {'x': 0, 'y': 0, 'width': 50, 'height': 20},
            'source_crop_sha256': sha('a'), 'roi_sha256': sha('b'),
            'status': 'candidate_unverified' if parsed is not None and confidence >= 0.75 else 'needs_manual_review',
            'requires_manual_review': True, 'poker_event_verified': False}


def report(*rows, rec='c', profile='d'):
    return {'schema_version': 1,
            'analysis_status': 'unverified_manual_roi_ocr_on_audited_navigation_crops',
            'recording_sha256': sha(rec), 'source_roi_config_sha256': sha(profile),
            'candidates': list(rows), 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False, 'requires_manual_review': True}


def review(*reports, **kwargs):
    return build_temporal_ocr_review([(r, sha(str(i % 10))) for i, r in enumerate(reports)], **kwargs)


class TemporalOCRReviewTests(unittest.TestCase):
    def test_pot_change_is_unverified_hint_not_math(self):
        result = review(report(candidate(1), candidate(2, 'Pot: 12.00')))
        self.assertEqual(result['counts']['possible_changes'], 1)
        self.assertEqual(result['review_items'][0]['kind'], 'possible_visual_value_change')
        self.assertFalse(result['hand_boundaries_verified'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])

    def test_unchanged_values_have_no_review_items(self):
        self.assertEqual(review(report(candidate(1), candidate(2)))['counts']['review_items'], 0)

    def test_four_tables_are_isolated(self):
        rows = [candidate(1, table=i) for i in range(1, 5)]
        rows += [candidate(2, 'Pot: 12.00' if i == 3 else 'Pot: 10.00', table=i)
                 for i in range(1, 5)]
        result = review(report(*rows))
        self.assertEqual(result['counts']['possible_changes'], 1)
        self.assertEqual(result['review_items'][0]['table_id'], 3)

    def test_fields_and_roi_coordinates_are_isolated(self):
        rows = [candidate(1), candidate(2, 'Pot: 12.00', roi={'x': 1, 'y': 0, 'width': 50, 'height': 20}),
                candidate(2, 'Bet: 10.00', field='bet')]
        self.assertEqual(review(report(*rows))['counts']['possible_changes'], 0)

    def test_duplicate_pts_are_ambiguous_even_when_values_match(self):
        result = review(report(candidate(1), candidate(1), candidate(2, 'Pot: 12.00')))
        self.assertEqual(result['counts']['possible_changes'], 0)
        self.assertEqual(result['counts']['ambiguous_or_uncertain'], 2)

    def test_unverified_pts_does_not_bridge(self):
        result = review(report(candidate(1), candidate(2, 'Pot: 12.00', verified=False),
                               candidate(3, 'Pot: 15.00')))
        self.assertEqual(result['counts']['possible_changes'], 0)
        self.assertEqual(result['counts']['ambiguous_or_uncertain'], 1)

    def test_low_confidence_and_unparsed_block_transition(self):
        low = candidate(2, 'Pot: 12.00', confidence=0.2)
        invalid = candidate(3, 'not-a-number')
        result = review(report(candidate(1), low, invalid, candidate(4, 'Pot: 15.00')))
        self.assertEqual(result['counts']['possible_changes'], 0)
        self.assertEqual(result['counts']['ambiguous_or_uncertain'], 2)

    def test_long_gap_does_not_imply_hand_boundary(self):
        result = review(report(candidate(1), candidate(100, 'Pot: 12.00')))
        self.assertEqual(result['counts']['possible_changes'], 0)
        self.assertEqual(result['review_items'][0]['kind'], 'gap_exceeds_comparison_window')

    def test_board_change_only_hint(self):
        result = review(report(candidate(1, 'As Kd Qc', field='board'),
                               candidate(2, 'As Kd Qc Jh', field='board')))
        self.assertEqual(result['counts']['possible_changes'], 1)
        self.assertFalse(result['cards_or_actions_verified'])

    def test_multiple_reports_same_recording(self):
        result = review(report(candidate(1)), report(candidate(2, 'Pot: 12.00')))
        self.assertEqual(result['counts']['possible_changes'], 1)
        with self.assertRaises(ValueError):
            review(report(candidate(1)), report(candidate(2), rec='e'))
        with self.assertRaises(ValueError):
            review(report(candidate(1)), report(candidate(2), profile='e'))

    def test_reject_forged_authority_and_parsed_value(self):
        a = report(candidate(1))
        a['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            review(a)
        a = report(candidate(1))
        a['candidates'][0]['parsed_candidate'] = 999
        with self.assertRaises(ValueError):
            review(a)
        a = report(candidate(1))
        a['candidates'][0]['poker_event_verified'] = True
        with self.assertRaises(ValueError):
            review(a)

    def test_reject_nan_bool_invalid_bounds(self):
        for value in [float('nan'), True, -1]:
            with self.subTest(value=str(value)):
                a = report(candidate(1))
                a['candidates'][0]['decoded_frame_pts_seconds'] = value
                with self.assertRaises(ValueError):
                    review(a)
        with self.assertRaises(ValueError):
            review(report(candidate(1)), max_candidates=0)
        with self.assertRaises(ValueError):
            review(report(candidate(1)), max_gap_seconds=float('inf'))

    def test_nonmonotonic_decoded_pts_blocks_comparison(self):
        a, b = candidate(1), candidate(2, 'Pot: 12.00')
        a['decoded_frame_pts_seconds'] = 5
        b['decoded_frame_pts_seconds'] = 4
        result = review(report(a, b))
        self.assertEqual(result['counts']['possible_changes'], 0)
        self.assertEqual(result['review_items'][0]['kind'], 'nonmonotonic_decoded_pts')

    def test_forged_candidate_status_rejected(self):
        a = report(candidate(1))
        a['candidates'][0]['status'] = 'human_confirmed'
        with self.assertRaises(ValueError):
            review(a)

    def test_budget_and_table_bounds(self):
        with self.assertRaises(ValueError):
            review(report(candidate(1), candidate(2)), max_candidates=1)
        with self.assertRaises(ValueError):
            review(report(candidate(1, table=5)))

    def test_export_cli_provenance_overwrite_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'ocr.json'
            p.write_text(json.dumps(report(candidate(1), candidate(2, 'Pot: 12.00'))))
            output = root / 'review.json'
            result = export_temporal_ocr_review([p], output)
            self.assertEqual(json.loads(output.read_text()), result)
            self.assertEqual(result['source_report_sha256s'], [hashlib.sha256(p.read_bytes()).hexdigest()])
            with self.assertRaises(ValueError):
                export_temporal_ocr_review([p], output)
            alias = root / 'alias.json'
            alias.symlink_to(p)
            with self.assertRaises(ValueError):
                export_temporal_ocr_review([alias], root / 'another.json')
            cli_out = root / 'cli.json'
            run = subprocess.run([sys.executable,
                                  str(Path(__file__).with_name('activity_crop_ocr_temporal_review.py')),
                                  str(p), '--output', str(cli_out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['possible_changes'], 1)
            self.assertTrue(cli_out.exists())


if __name__ == '__main__':
    unittest.main()
