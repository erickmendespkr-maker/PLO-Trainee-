"""Synthetic ROI queue -> bounded full-resolution OCR seek plan -> FFmpeg evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_evidence_export import audit_activity_evidence, export_activity_evidence
from activity_ocr_bridge import prepare_activity_ocr_jobs, scan_activity_ocr
from activity_roi_ocr_seek_plan import build_roi_ocr_seek_plan, write_roi_ocr_seek_plan
from activity_snapshot_chain import canonical_sha256
from table_regions import Region
from video_validator import validate_recording


def queue(sha, *, four_tables=False):
    # Candidate ranks sorted by synthetic pixel intensity, not poker quality.
    specs = [(3, 'hero_cards', 1., 3., .8),
             (4, 'board', 2., 4., .7),
             (3, 'pot', 1., 3., .6)]
    if four_tables:
        specs += [(1, 'board', 3., 5., .5), (2, 'pot', 4., 6., .4)]
    rows = []
    for rank, (table, label, start, end, diff) in enumerate(specs, 1):
        rows.append({'pixel_review_rank': rank, 'table_id': table,
                     'review_window_index': rank - 1,
                     'region_label_hypothesis': label,
                     'start_pts_seconds': start, 'end_pts_seconds': end,
                     'first_frame': f'images/table_{table:02d}/frame_00000.png',
                     'last_frame': f'images/table_{table:02d}/frame_00002.png',
                     'comparison_count': 2, 'peak_luma_difference': diff,
                     'confidence_in_region_mapping': 'not_calibrated',
                     'confidence_in_poker_semantics': 'not_calibrated',
                     'requires_manual_review': True})
    return {'schema_version': 1,
            'analysis_status': 'unverified_region_pixel_review_queue',
            'recording_sha256': sha,
            'source_region_change_hints_sha256': 'a'*64,
            'source_contact_sheet_sha256': 'b'*64,
            'source_region_profile_sha256': 'c'*64,
            'ranking_method': 'descending_peak_mean_absolute_luma_difference_only',
            'pixel_threshold': .12, 'merge_gap_seconds': 2., 'max_candidates': 100,
            'total_candidate_intervals': len(rows), 'omitted_due_to_budget': 0,
            'candidates': rows,
            'timestamp_semantics': 'decoded_source_pts_seconds_not_exact_hand_boundary',
            'requires_manual_review': True,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'ready_for_equity_or_ev': False,
            'strategic_error_established': False}


class RoiOcrSeekPlanTests(unittest.TestCase):
    SHA = 'f'*64

    def build(self, source=None, **kwargs):
        return build_roi_ocr_seek_plan(source if source is not None else queue(self.SHA),
                                       recording_sha256=self.SHA,
                                       duration_seconds=9, **kwargs)

    def test_three_seeks_and_deduplicated_cross_region(self):
        result = self.build()
        self.assertEqual(result['planned_total_frames'], 6)
        self.assertEqual(result['tables'][0]['table_id'], 3)
        self.assertEqual(result['tables'][0]['planned_count'], 3)
        self.assertEqual(result['tables'][1]['table_id'], 4)
        self.assertEqual(result['candidate_seek_associations'][2]['new_unique_table_seeks'], 0)
        self.assertEqual(result['source_roi_queue_sha256'], canonical_sha256(queue(self.SHA)))
        self.assertTrue(all(r['reason'] == 'unverified_activity_neighborhood'
                            for t in result['tables'] for r in t['requested_frames']))
        self.assertEqual(result['timestamp_semantics'], 'requested_seek_seconds_not_decoded_source_pts')
        for flag in ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
                     'automatic_clip_selection_authorized', 'strategic_error_established'):
            self.assertFalse(result[flag])

    def test_four_table_isolation(self):
        result = self.build(queue(self.SHA, four_tables=True))
        self.assertEqual([t['table_id'] for t in result['tables']], [1, 2, 3, 4])
        self.assertEqual(result['planned_total_frames'], 12)

    def test_budget_skips_whole_candidate_no_partial_claims(self):
        result = self.build(max_total_requests=3)
        self.assertEqual(result['planned_total_frames'], 3)
        self.assertEqual(len(result['candidate_seek_associations']), 2)
        self.assertEqual(len(result['skipped_candidates']), 1)
        self.assertEqual(result['skipped_candidates'][0]['reason'], 'request_budget_exhausted')
        self.assertEqual(result['candidate_seek_associations'][1]['new_unique_table_seeks'], 0)

    def test_close_interval_collapse_and_empty_rejected(self):
        q = queue(self.SHA)
        q['candidates'] = q['candidates'][:1]
        q['total_candidate_intervals'] = 1
        q['candidates'][0]['start_pts_seconds'] = 1.000000001
        q['candidates'][0]['end_pts_seconds'] = 1.000000002
        with self.assertRaisesRegex(ValueError, 'No valid resampling'):
            self.build(q)

    def test_invalid_parameters(self):
        for bad in (0, True, -1, 6, 1.2):
            with self.subTest(samples=bad), self.assertRaises(ValueError):
                self.build(samples_per_candidate=bad)
        for bad in (0, True, -1, 601, 1.2):
            with self.subTest(budget=bad), self.assertRaises(ValueError):
                self.build(max_total_requests=bad)
        for bad in (float('nan'), float('inf'), 0, True):
            with self.subTest(duration=bad), self.assertRaises(ValueError):
                build_roi_ocr_seek_plan(queue(self.SHA), recording_sha256=self.SHA,
                                        duration_seconds=bad)

    def test_reject_foreign_video_and_pinned_tampering(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.build(queue('0'*64))
        q = queue(self.SHA)
        digest = canonical_sha256(q)
        q['warning'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.build(q, expected_queue_sha256=digest)

    def test_reject_forged_authorizations(self):
        for flag in ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
                     'automatic_clip_selection_authorized', 'strategic_error_established'):
            q = queue(self.SHA)
            q[flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.build(q)

    def test_reject_malformed_roi_candidates(self):
        bad = [('table_id', True), ('table_id', 5), ('pixel_review_rank', 3),
               ('start_pts_seconds', float('nan')), ('end_pts_seconds', 99),
               ('peak_luma_difference', 1.1), ('comparison_count', 0),
               ('confidence_in_poker_semantics', 'verified'),
               ('requires_manual_review', False), ('first_frame', '../../etc/passwd'),
               ('last_frame', 'images/table_01/frame_00001.png')]
        for key, value in bad:
            q = queue(self.SHA)
            q['candidates'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.build(q)

    def test_reject_invalid_queue_counts_and_provenance(self):
        for key, value in [('total_candidate_intervals', 10), ('omitted_due_to_budget', -1),
                           ('max_candidates', True), ('source_contact_sheet_sha256', 'x'),
                           ('analysis_status', 'verified'), ('timestamp_semantics', 'wall_clock'),
                           ('ranking_method', 'strategic_importance')]:
            q = queue(self.SHA)
            q[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build(q)

    def test_deterministic_and_no_input_mutation(self):
        q = queue(self.SHA)
        before = copy.deepcopy(q)
        self.assertEqual(self.build(q), self.build(q))
        self.assertEqual(q, before)


class RoiOcrFFmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=4:duration=9',
                        '-c:v', 'mpeg4', str(cls.video)], check=True, capture_output=True)
        cls.sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_cli_ffmpeg_evidence_and_ocr_jobs(self):
        q = queue(self.sha)
        qp = self.root / 'roi_queue.json'
        qp.write_text(json.dumps(q), encoding='utf-8')
        plan_path = self.root / 'targeted_seek_plan.json'
        proc = subprocess.run([sys.executable, str(Path(__file__).with_name('activity_roi_ocr_seek_plan.py')),
                               str(qp), str(self.video), str(plan_path),
                               '--expected-queue-sha256', canonical_sha256(q)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        self.assertEqual(plan['planned_total_frames'], 6)
        self.assertEqual(plan['recording_sha256'], self.sha)
        regions = [Region(3, 0, 72, 128, 72), Region(4, 128, 72, 128, 72)]
        output = self.root / 'targeted_evidence'
        manifest = export_activity_evidence(self.video, plan, output, regions=regions)
        self.assertTrue(audit_activity_evidence(manifest, output)['ok'])
        rois = {'tasks': [{'table_id': 3, 'field': 'hero_cards',
                           'region': {'x': 0, 'y': 0, 'width': 100, 'height': 60}},
                          {'table_id': 4, 'field': 'board',
                           'region': {'x': 0, 'y': 0, 'width': 100, 'height': 60}}]}
        ocr_plan = prepare_activity_ocr_jobs(output, rois)
        self.assertGreater(ocr_plan['ocr_jobs'], 0)
        self.assertEqual(ocr_plan['recording_sha256'], self.sha)
        self.assertEqual(ocr_plan['ocr_jobs'], ocr_plan['unique_table_frames'])
        self.assertEqual({r['field'] for r in ocr_plan['jobs']}, {'hero_cards', 'board'})
        self.assertEqual({r['table_id'] for r in ocr_plan['jobs']}, {3, 4})
        self.assertTrue(all(r['source_sha256'] for r in ocr_plan['jobs']))
        self.assertFalse(plan['ready_for_equity_or_ev'])
        ocr_result = scan_activity_ocr(output, rois, self.root / 'ocr_candidates.json')
        self.assertEqual(len(ocr_result['candidates']), ocr_plan['ocr_jobs'])
        self.assertTrue(all(c['status'] in ('candidate_unverified', 'needs_manual_review')
                            for c in ocr_result['candidates']))
        self.assertFalse(ocr_result['ready_for_equity_or_ev'])

    def test_no_overwrite_or_wrong_video(self):
        q = queue(self.sha)
        qp = self.root / 'queue2.json'
        qp.write_text(json.dumps(q), encoding='utf-8')
        dest = self.root / 'existing.json'
        dest.write_text('original', encoding='utf-8')
        with self.assertRaises(ValueError):
            write_roi_ocr_seek_plan(qp, self.video, dest)
        self.assertEqual(dest.read_text(), 'original')
        q['recording_sha256'] = '0'*64
        qp.write_text(json.dumps(q), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'identity'):
            write_roi_ocr_seek_plan(qp, self.video, self.root / 'no_output.json')
        self.assertFalse((self.root / 'no_output.json').exists())


if __name__ == '__main__':
    unittest.main()
