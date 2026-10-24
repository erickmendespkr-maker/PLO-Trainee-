"""Synthetic regression checks; no claims about recognition of real PLO hands."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_boundary_contact_sheet import export_boundary_contact_sheet
from activity_visual_change_hints import (
    _difference, build_visual_change_hints, export_visual_change_hints)


class VisualChangeHintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_activity_boundary_contact_sheet import BoundaryContactSheetTests
        cls.base = BoundaryContactSheetTests
        BoundaryContactSheetTests.setUpClass()
        cls.packet_tmp = tempfile.TemporaryDirectory()
        cls.packet = Path(cls.packet_tmp.name) / 'contact_sheet'
        cls.report = export_boundary_contact_sheet(cls.base.plan_path,
                                                    cls.base.evidence, cls.packet)

    @classmethod
    def tearDownClass(cls):
        cls.packet_tmp.cleanup()
        cls.base.tearDownClass()

    def build(self, report=None, **kwargs):
        return build_visual_change_hints(report if report is not None else self.report,
                                         self.packet, **kwargs)

    def test_four_tables_and_twelve_audited_pngs(self):
        r = self.build()
        self.assertEqual(len(r['windows']), 4)
        self.assertEqual(r['resolved_images'], 12)
        self.assertEqual(r['unresolved_images'], 0)
        self.assertEqual({w['table_id'] for w in r['windows']}, {1, 2, 3, 4})
        self.assertEqual(sum(len(w['pairs']) for w in r['windows']), 8)
        self.assertTrue(all(p['status'] == 'unverified_pixel_change_hint'
                            for w in r['windows'] for p in w['pairs']))
        self.assertFalse(r['ready_for_equity_or_ev'])
        self.assertFalse(r['automatic_hand_boundaries_authorized'])
        self.assertFalse(r['strategic_error_established'])

    def test_determinism_and_pts(self):
        a, b = self.build(), self.build()
        self.assertEqual(a, b)
        for w in a['windows']:
            for p in w['pairs']:
                self.assertLess(p['left_decoded_pts_seconds'], p['right_decoded_pts_seconds'])
                self.assertGreaterEqual(p['mean_absolute_luma_difference'], 0)
                self.assertLessEqual(p['mean_absolute_luma_difference'], 1)
                self.assertEqual(len(p['top_middle_bottom_luma_differences']), 3)
                self.assertEqual(p['confidence_in_poker_semantics'], 'not_calibrated')

    def test_math_of_pixel_differences(self):
        black, white = bytes(48 * 48), bytes([255] * (48 * 48))
        self.assertEqual(_difference(black, black), (0.0, [0.0] * 3))
        self.assertEqual(_difference(black, white), (1.0, [1.0] * 3))

    def test_no_input_mutation(self):
        original = copy.deepcopy(self.report)
        self.build()
        self.assertEqual(original, self.report)

    def test_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'hints.json'
            r = export_visual_change_hints(self.packet, target)
            self.assertEqual(json.loads(target.read_text()), r)
            with self.assertRaises(ValueError):
                export_visual_change_hints(self.packet, target)

    def test_pinned_report_hash(self):
        with self.assertRaisesRegex(ValueError, 'report SHA-256'):
            self.build(expected_report_sha256='f' * 64)

    def test_tampered_png_is_rejected(self):
        path = self.packet / self.report['windows'][0]['frames'][0]['image']
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'altered')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                self.build()
        finally:
            path.write_bytes(original)

    def test_missing_png_is_rejected(self):
        path = self.packet / self.report['windows'][0]['frames'][0]['image']
        backup = path.with_suffix('.bak')
        path.rename(backup)
        try:
            with self.assertRaisesRegex(ValueError, 'Missing'):
                self.build()
        finally:
            backup.rename(path)

    def test_outside_interval_is_skipped(self):
        r = copy.deepcopy(self.report)
        w = r['windows'][0]
        w['candidate_interval_pts'][1] = w['frames'][1]['decoded_source_pts_seconds'] + .001
        # Last decoded PTS now falls outside candidate interval, but requested
        # seek remains interior only if new end exceeds the last requested seek.
        w['candidate_interval_pts'][1] = max(w['frames'][-1]['requested_seek_seconds'] + .01,
                                            w['frames'][1]['decoded_source_pts_seconds'] + .001)
        if w['frames'][-1]['decoded_source_pts_seconds'] > w['candidate_interval_pts'][1]:
            w['frames'][-1]['status'] = 'decoded_outside_candidate_interval_review_required'
            self.assertEqual(self.build(r)['windows'][0]['pairs'][-1]['status'],
                             'outside_interval_prevents_comparison')
        else:
            # Explicit inconsistent relabelling must be rejected.
            w['frames'][-1]['status'] = 'decoded_outside_candidate_interval_review_required'
            with self.assertRaises(ValueError):
                self.build(r)

    def test_unresolved_seek_skips_adjacent_pairs(self):
        r = copy.deepcopy(self.report)
        f = r['windows'][0]['frames'][1]
        f.update(status='no_decoded_frame', image=None, decoded_source_pts_seconds=None)
        r['resolved_count'] -= 1
        r['unresolved_count'] += 1
        x = self.build(r)
        self.assertEqual(x['windows'][0]['pairs'][0]['status'],
                         'unresolved_frame_prevents_comparison')

    def test_reject_unauthorized_statuses(self):
        for field in ('ready_for_equity_or_ev', 'strategic_error_established',
                      'automatic_clip_selection_authorized', 'automatic_hand_boundaries_authorized'):
            with self.subTest(field=field):
                r = copy.deepcopy(self.report)
                r[field] = True
                with self.assertRaises(ValueError):
                    self.build(r)

    def test_reject_path_traversal_and_wrong_table(self):
        for name in ('../../evil.png', 'images/table_04/frame_00001.png'):
            r = copy.deepcopy(self.report)
            r['windows'][0]['frames'][0]['image'] = name
            with self.assertRaises(ValueError):
                self.build(r)

    def test_reject_boolean_limits_and_thresholds(self):
        for options in ({'max_images': True}, {'max_total_png_bytes': True},
                        {'change_threshold': True}, {'change_threshold': 1.1},
                        {'max_images': 1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.build(**options)

    def test_reject_count_mismatch(self):
        r = copy.deepcopy(self.report)
        r['resolved_count'] += 1
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            self.build(r)

    def test_reject_duplicate_image_reference(self):
        r = copy.deepcopy(self.report)
        r['windows'][0]['frames'][1]['image'] = r['windows'][0]['frames'][0]['image']
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            self.build(r)

    def test_reject_wrong_pts_status(self):
        r = copy.deepcopy(self.report)
        r['windows'][0]['frames'][0]['status'] = 'decoded_outside_candidate_interval_review_required'
        with self.assertRaises(ValueError):
            self.build(r)


if __name__ == '__main__':
    unittest.main()
