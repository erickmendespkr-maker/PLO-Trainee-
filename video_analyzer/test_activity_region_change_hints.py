"""Offline synthetic tests; pixel change is not poker recognition."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_snapshot_chain import canonical_sha256
from activity_boundary_contact_sheet import export_boundary_contact_sheet
from activity_region_change_hints import (
    _roi_difference, build_region_change_hints, export_region_change_hints)


class RegionChangeHintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_activity_boundary_contact_sheet import BoundaryContactSheetTests
        cls.base = BoundaryContactSheetTests
        cls.base.setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.packet = cls.root / 'packet'
        cls.report = export_boundary_contact_sheet(cls.base.plan_path,
                                                   cls.base.evidence, cls.packet)
        cls.profile = {'schema_version': 1, 'profile_status': 'manual_unverified_regions',
                       'calibration_verified': False,
                       'recording_sha256': cls.report['recording_sha256'],
                       'tables': [{'table_id': i, 'regions': {
                           'board': [0.0, 0.0, 1.0, .33],
                           'hero_cards': [0.0, .33, 1.0, .34],
                           'pot': [0.0, .67, 1.0, .33]}} for i in range(1, 5)]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.base.tearDownClass()

    def build(self, profile=None, report=None, **kwargs):
        return build_region_change_hints(
            self.report if report is None else report, self.packet,
            self.profile if profile is None else profile, **kwargs)

    def test_four_tables_eight_pairs_three_regions(self):
        out = self.build()
        self.assertEqual(len(out['windows']), 4)
        self.assertEqual(sum(len(w['pairs']) for w in out['windows']), 8)
        self.assertEqual(sum(len(p['regions']) for w in out['windows']
                             for p in w['pairs']), 24)
        self.assertEqual(out['analysis_status'], 'unverified_manual_roi_pixel_change_hints')
        self.assertFalse(out['ready_for_equity_or_ev'])
        self.assertFalse(out['automatic_clip_selection_authorized'])
        self.assertFalse(out['automatic_hand_boundaries_authorized'])
        self.assertFalse(out['strategic_error_established'])

    def test_deterministic_and_provenance(self):
        a, b = self.build(), self.build()
        self.assertEqual(a, b)
        self.assertEqual(a['source_contact_sheet_sha256'], canonical_sha256(self.report))
        self.assertEqual(a['source_region_profile_sha256'], canonical_sha256(self.profile))
        for w in a['windows']:
            for pair in w['pairs']:
                self.assertLess(pair['left_decoded_pts_seconds'],
                                pair['right_decoded_pts_seconds'])
                for region in pair['regions']:
                    self.assertTrue(0 <= region['mean_absolute_luma_difference'] <= 1)
                    self.assertEqual(region['confidence_in_poker_semantics'],
                                     'not_calibrated')

    def test_roi_math(self):
        black = bytes(48 * 48)
        white = bytes([255] * (48 * 48))
        self.assertEqual(_roi_difference(black, black, (0, 0, 48, 16)), 0)
        self.assertEqual(_roi_difference(black, white, (0, 0, 48, 16)), 1)
        part = bytes([255] * (48 * 16) + [0] * (48 * 32))
        self.assertEqual(_roi_difference(black, part, (0, 0, 48, 16)), 1)
        self.assertEqual(_roi_difference(black, part, (0, 16, 48, 48)), 0)

    def test_no_mutation(self):
        before = copy.deepcopy(self.profile)
        self.build()
        self.assertEqual(before, self.profile)

    def test_export_and_no_overwrite(self):
        profile_path = self.root / 'profile.json'
        profile_path.write_text(json.dumps(self.profile))
        target = self.root / 'result.json'
        try:
            out = export_region_change_hints(self.packet, profile_path, target)
            self.assertEqual(json.loads(target.read_text()), out)
            with self.assertRaises(ValueError):
                export_region_change_hints(self.packet, profile_path, target)
        finally:
            target.unlink(missing_ok=True)
            profile_path.unlink(missing_ok=True)

    def test_pinned_hashes(self):
        with self.assertRaisesRegex(ValueError, 'ROI profile SHA-256'):
            self.build(expected_profile_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'report SHA-256'):
            self.build(expected_report_sha256='0' * 64)

    def test_missing_region_table_requires_review(self):
        p = copy.deepcopy(self.profile)
        p['tables'] = p['tables'][:1]
        out = self.build(profile=p)
        self.assertEqual(out['windows'][1]['pairs'][0]['status'],
                         'unconfigured_regions_requires_manual_review')
        self.assertEqual(out['windows'][1]['pairs'][0]['regions'], [])

    def test_reject_premature_calibration(self):
        p = copy.deepcopy(self.profile)
        p['calibration_verified'] = True
        with self.assertRaises(ValueError):
            self.build(profile=p)

    def test_reject_wrong_recording(self):
        p = copy.deepcopy(self.profile)
        p['recording_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.build(profile=p)

    def test_reject_duplicate_table(self):
        p = copy.deepcopy(self.profile)
        p['tables'][1]['table_id'] = 1
        with self.assertRaises(ValueError):
            self.build(profile=p)

    def test_reject_bad_region_labels(self):
        p = copy.deepcopy(self.profile)
        p['tables'][0]['regions']['fold_probability'] = [0, 0, .5, .5]
        with self.assertRaises(ValueError):
            self.build(profile=p)

    def test_reject_invalid_rectangles(self):
        bad = ([0, 0, 1.1, .3], [-.1, 0, .2, .2], [0, 0, .01, .01],
               [0, 0, float('nan'), .3], [0, 0, True, .5], [0, 0, .5],
               [.4, .4, .8, .8], [0, 0, 0, .5])
        for rect in bad:
            with self.subTest(rect=rect):
                p = copy.deepcopy(self.profile)
                p['tables'][0]['regions']['board'] = rect
                with self.assertRaises(ValueError):
                    self.build(profile=p)

    def test_reject_invalid_threshold(self):
        for value in (True, 0, 1, -1, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.build(pixel_threshold=value)

    def test_reject_unauthorized_contact_sheet(self):
        r = copy.deepcopy(self.report)
        r['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            self.build(report=r)

    def test_reject_png_tampering(self):
        path = self.packet / self.report['windows'][0]['frames'][0]['image']
        data = path.read_bytes()
        try:
            path.write_bytes(data + b'tamper')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                self.build()
        finally:
            path.write_bytes(data)

    def test_reject_symlinked_table_directory(self):
        original = self.packet / 'images' / 'table_04'
        backup = self.packet / 'images' / 'table_04_backup'
        original.rename(backup)
        try:
            original.symlink_to(backup, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.build()
        finally:
            original.unlink(missing_ok=True)
            backup.rename(original)

    def test_unresolved_frame_stays_unresolved(self):
        r = copy.deepcopy(self.report)
        f = r['windows'][0]['frames'][1]
        f.update(status='no_decoded_frame', image=None, decoded_source_pts_seconds=None)
        r['resolved_count'] -= 1
        r['unresolved_count'] += 1
        out = self.build(report=r)
        self.assertEqual(out['windows'][0]['pairs'][0]['status'],
                         'unresolved_frame_prevents_comparison')
        self.assertEqual(out['windows'][0]['pairs'][0]['regions'], [])


if __name__ == '__main__':
    unittest.main()
