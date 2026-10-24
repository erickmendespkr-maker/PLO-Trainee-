"""Synthetic offline tests: review queue is not poker event detection."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_region_review_queue import (
    _group_candidates, build_region_review_queue, export_region_review_queue)
from activity_snapshot_chain import canonical_sha256


class RegionReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_activity_region_change_hints import RegionChangeHintTests
        cls.base = RegionChangeHintTests
        cls.base.setUpClass()
        cls.packet, cls.report, cls.profile = cls.base.packet, cls.base.report, cls.base.profile
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.base.tearDownClass()

    def build(self, **kwargs):
        return build_region_review_queue(self.report, self.packet, self.profile, **kwargs)

    def test_four_tables_provenance_and_no_authorization(self):
        out = self.build()
        self.assertEqual(out['analysis_status'], 'unverified_region_pixel_review_queue')
        self.assertEqual(out['source_contact_sheet_sha256'], canonical_sha256(self.report))
        self.assertEqual(out['source_region_profile_sha256'], canonical_sha256(self.profile))
        self.assertTrue(out['requires_manual_review'])
        for key in ('automatic_hand_boundaries_authorized',
                    'automatic_clip_selection_authorized', 'ready_for_equity_or_ev',
                    'strategic_error_established'):
            self.assertFalse(out[key])
        self.assertEqual(out['total_candidate_intervals'], len(out['candidates']))
        self.assertTrue(out['candidates'])
        self.assertTrue({c['table_id'] for c in out['candidates']} <= {1, 2, 3, 4})
        for candidate in out['candidates']:
            self.assertLess(candidate['start_pts_seconds'], candidate['end_pts_seconds'])
            self.assertEqual(candidate['confidence_in_poker_semantics'], 'not_calibrated')

    def test_deterministic_rank_and_budget(self):
        a, b = self.build(), self.build()
        self.assertEqual(a, b)
        self.assertEqual([c['pixel_review_rank'] for c in a['candidates']],
                         list(range(1, len(a['candidates']) + 1)))
        self.assertEqual([c['peak_luma_difference'] for c in a['candidates']],
                         sorted((c['peak_luma_difference'] for c in a['candidates']), reverse=True))
        limited = self.build(max_candidates=1)
        self.assertEqual(len(limited['candidates']), 1)
        self.assertEqual(limited['omitted_due_to_budget'],
                         a['total_candidate_intervals'] - 1)
        self.assertEqual(limited['candidates'][0], a['candidates'][0])

    def test_invalid_budget_and_gap(self):
        for bad in (0, True, -1, 1001, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.build(max_candidates=bad)
        for bad in (0, -1, True, float('nan'), float('inf'), 61):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.build(merge_gap_seconds=bad)

    def test_group_contiguous_pairs_but_not_missing_or_unchanged(self):
        def pair(a, b, value, flag=True):
            return {'status': 'unverified_region_pixel_change_hints',
                    'left_image': f'{a}.png', 'right_image': f'{b}.png',
                    'left_decoded_pts_seconds': float(a),
                    'right_decoded_pts_seconds': float(b),
                    'regions': [{'region_label_hypothesis': 'board',
                                 'mean_absolute_luma_difference': value,
                                 'above_fixed_pixel_threshold': flag}]}
        report = {'windows': [{'table_id': 1, 'review_window_index': 0,
                              'pairs': [pair(1, 2, .3), pair(2, 3, .5),
                                        pair(3, 4, .01, False), pair(4, 5, .8),
                                        {'status': 'unresolved_frame_prevents_comparison'},
                                        pair(6, 7, .6)]},
                             {'table_id': 2, 'review_window_index': 0,
                              'pairs': [pair(1, 2, .9)]}]}
        items = _group_candidates(report, 2)
        self.assertEqual(len(items), 4)
        self.assertEqual([(c['table_id'], c['start_pts_seconds'],
                           c['end_pts_seconds'], c['comparison_count']) for c in items],
                         [(1, 1., 3., 2), (1, 4., 5., 1),
                          (1, 6., 7., 1), (2, 1., 2., 1)])
        self.assertEqual(items[0]['peak_luma_difference'], .5)

    def test_does_not_merge_time_gap_or_frame_discontinuity(self):
        def p(a, b, left, right):
            return {'status': 'unverified_region_pixel_change_hints',
                    'left_image': left, 'right_image': right,
                    'left_decoded_pts_seconds': a, 'right_decoded_pts_seconds': b,
                    'regions': [{'region_label_hypothesis': 'pot',
                                 'mean_absolute_luma_difference': .3,
                                 'above_fixed_pixel_threshold': True}]}
        data = {'windows': [{'table_id': 1, 'review_window_index': 0,
                            'pairs': [p(1, 2, 'a', 'b'), p(2, 6, 'b', 'c'),
                                      p(6, 7, 'different', 'd')]}]}
        self.assertEqual(len(_group_candidates(data, 2)), 3)

    def test_no_mutation(self):
        report_before, profile_before = copy.deepcopy(self.report), copy.deepcopy(self.profile)
        self.build()
        self.assertEqual(self.report, report_before)
        self.assertEqual(self.profile, profile_before)

    def test_reject_source_tampering(self):
        modified = copy.deepcopy(self.profile)
        modified['calibration_verified'] = True
        with self.assertRaises(ValueError):
            build_region_review_queue(self.report, self.packet, modified)
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.build(expected_report_sha256='0' * 64)

    def test_export_and_no_overwrite(self):
        profile_path, output = self.root / 'profile.json', self.root / 'queue.json'
        profile_path.write_text(json.dumps(self.profile), encoding='utf-8')
        result = export_region_review_queue(self.packet, profile_path, output)
        self.assertEqual(result, json.loads(output.read_text(encoding='utf-8')))
        with self.assertRaises(ValueError):
            export_region_review_queue(self.packet, profile_path, output)


    def test_no_candidates_with_high_threshold(self):
        out = self.build(pixel_threshold=.999999)
        self.assertEqual(out['total_candidate_intervals'], 0)
        self.assertEqual(out['candidates'], [])
        self.assertFalse(out['automatic_clip_selection_authorized'])

    def test_missing_profile_table_is_not_inferred(self):
        profile = copy.deepcopy(self.profile)
        profile['tables'] = profile['tables'][:1]
        out = build_region_review_queue(self.report, self.packet, profile)
        self.assertTrue(all(c['table_id'] == 1 for c in out['candidates']))

    def test_tampered_png_rejected(self):
        path = self.packet / self.report['windows'][0]['frames'][0]['image']
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'altered')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                self.build()
        finally:
            path.write_bytes(original)

    def test_cli(self):
        import subprocess
        import sys
        script = Path(__file__).with_name('activity_region_review_queue.py')
        profile_path, output = self.root / 'cli_profile.json', self.root / 'cli_queue.json'
        profile_path.write_text(json.dumps(self.profile), encoding='utf-8')
        result = subprocess.run([sys.executable, str(script), str(self.packet),
                                 str(profile_path), str(output), '--max-candidates', '2'],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(output.read_text())['candidates']), 2)


if __name__ == '__main__':
    unittest.main()
