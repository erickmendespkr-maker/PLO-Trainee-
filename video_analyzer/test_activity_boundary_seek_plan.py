"""Synthetic integration: reviewed intervals -> requested seeks -> real FFmpeg PTS."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from activity_boundary_seek_plan import build_boundary_seek_plan, write_boundary_seek_plan
from activity_evidence_export import audit_activity_evidence, export_activity_evidence
from activity_hand_boundary_review import build_hand_boundary_review
from activity_reviewed_hand_timeline import build_reviewed_hand_timeline
from hand_history import Observation
from dataclasses import asdict
from test_activity_reviewed_hand_timeline import fixture as four_table_fixture
from activity_snapshot_chain import canonical_sha256
from test_activity_hand_boundary_review import timeline
from video_validator import validate_recording

SHA = 'b' * 64


def four_table_report(sha):
    reviewed = four_table_fixture()
    reviewed['recording_sha256'] = sha
    for table in range(1, 5):
        for timestamp, action in ((7, 'hand_start'), (8, 'hand_end')):
            idx = len(reviewed['observations'])
            reviewed['observations'].append(asdict(Observation(
                table, timestamp, action, .9, f'h{table}_second', variant='PLO5')))
            reviewed['provenance'].append({
                'event_index': idx, 'table_id': table, 'timestamp': timestamp,
                'hand_id': f'h{table}_second', 'human_confirmed': True, 'evidence': []})
    return build_hand_boundary_review(build_reviewed_hand_timeline(reviewed))


def report(sha=SHA):
    t = timeline()
    t['recording_sha256'] = sha
    return build_hand_boundary_review(t)


def plan(review=None, **kwargs):
    return build_boundary_seek_plan(review if review is not None else report(),
                                    recording_sha256=SHA, duration_seconds=9, **kwargs)


class BoundarySeekPlanTests(unittest.TestCase):
    def test_three_interior_seeks_and_source_hashes(self):
        result = plan()
        self.assertEqual(result['planned_total_frames'], 3)
        self.assertEqual(result['tables'][0]['table_id'], 1)
        self.assertEqual([r['requested_seek_seconds'] for r in result['tables'][0]['requested_frames']],
                         [4.5, 5., 5.5])
        self.assertEqual(result['review_window_seek_associations'][0]['candidate_interval_pts'], [4, 6])
        self.assertEqual(result['source_boundary_review_sha256'], canonical_sha256(report()))
        self.assertEqual(result['source_timeline_sha256'], report()['source_timeline_sha256'])
        self.assertFalse(result['automatic_hand_boundaries_authorized'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['strategic_error_established'])
        self.assertIn('not decoded PTS', result['warning'])

    def test_one_sample_center(self):
        result = plan(samples_per_window=1)
        self.assertEqual(result['tables'][0]['requested_frames'][0]['requested_seek_seconds'], 5)

    def test_missing_interval_never_fabricates_seeks(self):
        r = report()
        w = r['inter_hand_review_windows'][0]
        w['candidate_interval_pts'] = None
        w['next_first_observed_pts'] = w['previous_last_observed_pts']
        w['gap_seconds'] = None
        with self.assertRaises(ValueError):
            plan(r)

    def test_zero_width_from_valid_upstream_skipped(self):
        t = timeline()
        t['recording_sha256'] = SHA
        h = next(h for h in t['hands'] if h['hand_id_human_assigned'] == 'second')
        h['events'][0]['timestamp'] = 4
        h['first_observed_pts'] = 4
        with self.assertRaisesRegex(ValueError, 'No valid interior review seeks'):
            plan(build_hand_boundary_review(t))

    def test_reject_foreign_recording(self):
        with self.assertRaisesRegex(ValueError, 'recording identity'):
            plan(report('c'*64))

    def test_reject_tampered_report_when_pinned(self):
        r = report()
        pin = canonical_sha256(r)
        r['warning'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            plan(r, expected_review_sha256=pin)

    def test_reject_forged_authorizations(self):
        for key in ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
                    'automatic_clip_selection_authorized', 'strategic_error_established'):
            with self.subTest(key=key):
                r = report()
                r[key] = True
                with self.assertRaises(ValueError):
                    plan(r)

    def test_reject_inconsistent_window(self):
        for key, value in [('candidate_interval_pts', [4, 7]),
                           ('previous_last_observed_pts', 3),
                           ('next_first_observed_pts', 7),
                           ('gap_seconds', 10),
                           ('exact_boundary_known', True),
                           ('hand_assignment_automated', True),
                           ('status', 'confirmed'),
                           ('table_id', 5),
                           ('previous_hand_id_human_assigned', 'unknown')]:
            with self.subTest(key=key):
                r = report()
                r['inter_hand_review_windows'][0][key] = value
                with self.assertRaises(ValueError):
                    plan(r)

    def test_reject_wrong_counts_and_spans(self):
        for change in ('count', 'span', 'duplicate'):
            r = report()
            if change == 'count':
                r['counts']['inter_hand_windows'] = 99
            elif change == 'span':
                r['observed_hand_spans'][0]['last_observed_pts'] = 20
            else:
                r['inter_hand_review_windows'].append(copy.deepcopy(r['inter_hand_review_windows'][0]))
                r['counts']['inter_hand_windows'] += 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan(r)

    def test_reject_invalid_parameters(self):
        for params in ({'samples_per_window': 0}, {'samples_per_window': True},
                       {'samples_per_window': 6}, {'max_total_requests': 0},
                       {'max_total_requests': True}, {'max_total_requests': 601},
                       {'min_spacing_seconds': float('nan')},
                       {'min_spacing_seconds': -1},
                       {'min_spacing_seconds': True},
                       {'min_spacing_seconds': 31}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                plan(**params)

    def test_budget_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            plan(max_total_requests=2)

    def test_min_spacing_removes_dense_seeks_without_fabrication(self):
        result = plan(min_spacing_seconds=1)
        self.assertEqual(result['planned_total_frames'], 2)
        self.assertEqual([r['requested_seek_seconds'] for r in result['tables'][0]['requested_frames']],
                         [4.5, 5.5])

    def test_no_mutation(self):
        r = report()
        before = copy.deepcopy(r)
        plan(r)
        self.assertEqual(r, before)

    def test_reject_nonfinite_duration(self):
        for duration in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                build_boundary_seek_plan(report(), recording_sha256=SHA,
                                         duration_seconds=duration)


class FFmpegBoundaryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.temp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=4:duration=9',
                        '-c:v', 'mpeg4', str(cls.video)], capture_output=True, check=True)
        cls.sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_ffmpeg_pts_hashes_and_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            r = report(self.sha)
            p = build_boundary_seek_plan(r, recording_sha256=self.sha,
                                         duration_seconds=validate_recording(self.video)['duration_seconds'])
            root = Path(temp) / 'evidence'
            manifest = export_activity_evidence(self.video, p, root)
            self.assertEqual(manifest['resolved_count'], 3)
            self.assertEqual(manifest['unresolved_count'], 0)
            self.assertEqual([f['timestamp_seconds'] for f in manifest['frames']],
                             [4.5, 5., 5.5])
            self.assertTrue(audit_activity_evidence(manifest, root)['ok'])
            self.assertEqual({f['table_id'] for f in manifest['frames']}, {1})
            self.assertTrue(all(f['status'] == 'unverified_visual_evidence'
                                for f in manifest['frames']))

    def test_four_tables_12_pngs_audited(self):
        with tempfile.TemporaryDirectory() as temp:
            r = four_table_report(self.sha)
            p = build_boundary_seek_plan(r, recording_sha256=self.sha,
                                         duration_seconds=validate_recording(self.video)['duration_seconds'])
            self.assertEqual(p['planned_total_frames'], 12)
            self.assertEqual(len(p['tables']), 4)
            root = Path(temp) / 'evidence'
            manifest = export_activity_evidence(self.video, p, root)
            self.assertEqual(manifest['resolved_count'], 12)
            self.assertEqual(len({f['table_id'] for f in manifest['frames']}), 4)
            self.assertTrue(audit_activity_evidence(manifest, root)['ok'])
            self.assertEqual(len(list(root.rglob('*.png'))), 12)

    def test_cli_file_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            src, out = Path(temp)/'review.json', Path(temp)/'plan.json'
            r = report(self.sha)
            src.write_text(json.dumps(r), encoding='utf-8')
            p = write_boundary_seek_plan(src, self.video, out,
                                         expected_review_sha256=canonical_sha256(r))
            self.assertEqual(json.loads(out.read_text()), p)
            with self.assertRaises(ValueError):
                write_boundary_seek_plan(src, self.video, out)
            with self.assertRaises(ValueError):
                write_boundary_seek_plan(src, self.video, src)

    def test_wrong_video_digest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp)/'review.json'
            src.write_text(json.dumps(report()), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'recording identity'):
                write_boundary_seek_plan(src, self.video, Path(temp)/'plan.json')

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp)/'review.json'
            src.write_text(json.dumps(report(self.sha)), encoding='utf-8')
            link = Path(temp)/'linked.json'
            link.symlink_to(src)
            with self.assertRaises(ValueError):
                write_boundary_seek_plan(link, self.video, Path(temp)/'plan.json')


if __name__ == '__main__':
    unittest.main()
