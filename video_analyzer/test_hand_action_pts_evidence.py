"""Synthetic FFmpeg integration tests; no real poker footage or strategic claims."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from boundary_hand_draft import build_template, validate_review
from hand_action_pts_evidence import build_plan, export
from test_hand_evidence_link import example


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActionPTSEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp.name) / 'recording.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=5:duration=4',
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        nav, _, _, _, _, _, _ = example(self.root)
        nav['recording_sha256'] = sha(self.video)
        self.nav_path = self.root / 'navigation.json'
        self.nav_path.write_text(json.dumps(nav))
        self.nav_sha = sha(self.nav_path)
        self.nav = nav
        edited = build_template(nav, self.nav_sha)
        row = edited['entries'][0]
        row['reviewer'] = 'synthetic reviewer'
        row['fields']['variant'] = {'value': 'PLO5', 'confidence': 0.8,
            'source_pts_seconds': 1.1, 'source_kind': 'manual_video_review',
            'human_confirmed': True}
        row['fields']['pot_observed'] = {'value': 10, 'confidence': 0.5,
            'source_pts_seconds': 2.0, 'source_kind': 'manual_video_review',
            'human_confirmed': True}
        row['fields']['board_visible'] = {'value': ['As', 'Kd', 'Qc'],
            'confidence': 0.2, 'source_pts_seconds': None,
            'source_kind': 'hypothesis', 'human_confirmed': False}
        row['actions'] = [{'timestamp_seconds': 3.05, 'actor': 'hero',
            'action': 'call', 'amount': 2, 'confidence': 0.8,
            'source_kind': 'manual_video_review', 'human_confirmed': True}]
        self.review = validate_review(nav, self.nav_sha, edited)
        self.review_path = self.root / 'review.json'
        self.review_path.write_text(json.dumps(self.review))
        self.regions = self.root / 'regions.json'
        self.rects = {str(i): {'x': ((i - 1) % 2) * 160,
            'y': ((i - 1) // 2) * 120, 'width': 160, 'height': 120}
            for i in range(1, 5)}
        self.regions.write_text(json.dumps(self.rects))
        self.output = self.root / 'action_evidence'

    def run_export(self, **kwargs):
        return export(self.video, self.nav_path, self.review_path, self.output,
                      regions_json=self.regions, **kwargs)

    def test_four_tables_and_second_decode(self):
        result = self.run_export()
        self.assertEqual(result['counts']['human_confirmed_requests'], 3)
        self.assertEqual(result['counts']['frames_planned'], 3)
        self.assertEqual(result['counts']['pts_byte_matched'], 3)
        self.assertEqual(result['counts']['near_requested_pts'], 3)
        self.assertEqual({x['table_id'] for x in result['frames']}, {1})
        self.assertEqual(len(result['associations']), 3)
        self.assertEqual(json.loads((self.output / 'action_pts_evidence.json').read_text()), result)
        for row in result['frames']:
            self.assertEqual(sha(self.output / row['filename']), row['png_sha256'])
            self.assertTrue(row['within_requested_pts_tolerance'])
            self.assertIsNotNone(row['decoded_pts_seconds'])
            self.assertEqual(row['region'], self.rects['1'])
        for flag in ('ready_for_equity_or_ev', 'cards_or_actions_verified',
                     'automatic_clip_selection_authorized', 'strategic_error_established'):
            self.assertIs(result[flag], False)
        self.assertTrue(result['requires_manual_review'])

    def test_four_tables_separate_pngs(self):
        edited = build_template(self.nav, self.nav_sha)
        for row in edited['entries']:
            row['reviewer'] = 'synthetic reviewer'
            row['fields']['variant'] = {'value': 'PLO5', 'confidence': 0.9,
                'source_pts_seconds': 1.1, 'source_kind': 'manual_video_review',
                'human_confirmed': True}
            row['actions'] = [{'timestamp_seconds': 2.0, 'actor': 'hero',
                'action': 'check', 'amount': None, 'confidence': 0.7,
                'source_kind': 'manual_video_review', 'human_confirmed': True}]
        review = validate_review(self.nav, self.nav_sha, edited)
        self.review_path.write_text(json.dumps(review))
        result = self.run_export()
        self.assertEqual(result['counts']['frames_planned'], 8)
        self.assertEqual(result['counts']['near_requested_pts'], 8)
        self.assertEqual({x['table_id'] for x in result['frames']}, {1, 2, 3, 4})
        self.assertEqual(len({x['filename'] for x in result['frames']}), 8)
        self.assertTrue(all(x['filename'].startswith(
            f"action_table_{x['table_id']:02d}_") for x in result['frames']))

    def test_second_decode_mismatch_never_claims_pts(self):
        from hand_action_pts_evidence import _decode
        counter = {'n': 0}
        def disagree(*args, **kwargs):
            value = _decode(*args, **kwargs)
            counter['n'] += 1
            if counter['n'] % 2 == 0:
                return {**value, 'sha256': '0' * 64}
            return value
        with patch('hand_action_pts_evidence._decode', side_effect=disagree):
            result = self.run_export(max_frames=1)
        row = result['frames'][0]
        self.assertFalse(row['pts_byte_matched'])
        self.assertFalse(row['within_requested_pts_tolerance'])
        self.assertIsNone(row['decoded_pts_seconds'])
        self.assertEqual(result['counts']['near_requested_pts'], 0)

    def test_hypothesis_and_unknown_never_extracted(self):
        plan = build_plan(self.video, self.nav, self.nav_sha, self.review,
                          table_regions=self.rects)
        self.assertEqual(len(plan['associations']), 3)
        self.assertFalse(any(a['item'] == 'board_visible' for a in plan['associations']))
        self.assertFalse(any(a['item'] == 'hero_cards_visible' for a in plan['associations']))

    def test_budget_skips_without_fabrication(self):
        result = self.run_export(max_frames=1)
        self.assertEqual(result['counts']['frames_planned'], 1)
        self.assertEqual(result['counts']['requests_skipped'], 2)
        self.assertTrue(all(x['reason'] == 'frame_budget_exceeded' for x in result['skipped']))

    def test_multi_table_without_regions_rejected(self):
        with self.assertRaisesRegex(ValueError, 'region'):
            build_plan(self.video, self.nav, self.nav_sha, self.review)

    def test_invalid_region_rejected(self):
        self.rects['1']['width'] = 999
        with self.assertRaises(ValueError):
            build_plan(self.video, self.nav, self.nav_sha, self.review,
                       table_regions=self.rects)

    def test_tampered_review_authority_rejected(self):
        self.review['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_plan(self.video, self.nav, self.nav_sha, self.review,
                       table_regions=self.rects)

    def test_video_digest_mismatch_rejected(self):
        self.nav['recording_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            build_plan(self.video, self.nav, self.nav_sha, self.review,
                       table_regions=self.rects)

    def test_no_overwrite(self):
        self.run_export(max_frames=1)
        with self.assertRaises(ValueError):
            self.run_export(max_frames=1)

    def test_no_symlink_input(self):
        alias = self.root / 'video_link.mp4'
        alias.symlink_to(self.video)
        with self.assertRaises(ValueError):
            export(alias, self.nav_path, self.review_path, self.output,
                   regions_json=self.regions)

    def test_duplicate_json_keys_rejected(self):
        self.review_path.write_text('{"entries":[],"entries":[]}')
        with self.assertRaises(ValueError):
            self.run_export()

    def test_unverified_pts_fails_closed(self):
        with patch('hand_action_pts_evidence._parse_decoded_pts', side_effect=ValueError('bad PTS')):
            with self.assertRaisesRegex(ValueError, 'bad PTS'):
                self.run_export(max_frames=1)
        self.assertFalse(self.output.exists())

    def test_nonfinite_or_bool_budget_rejected(self):
        for n in (True, 0, 121, 1.2):
            with self.subTest(n=n), self.assertRaises(ValueError):
                build_plan(self.video, self.nav, self.nav_sha, self.review,
                           max_frames=n, table_regions=self.rects)

    def test_reject_out_of_span_pts(self):
        self.review['entries'][0]['fields']['variant']['source_pts_seconds'] = 999.0
        with self.assertRaises(ValueError):
            build_plan(self.video, self.nav, self.nav_sha, self.review,
                       table_regions=self.rects)


if __name__ == '__main__':
    unittest.main()
