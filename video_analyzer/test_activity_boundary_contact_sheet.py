"""Synthetic-only regression checks for offline inter-hand contact sheets."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from activity_boundary_contact_sheet import build_boundary_contact_sheet, export_boundary_contact_sheet
from activity_boundary_seek_plan import build_boundary_seek_plan
from activity_evidence_export import export_activity_evidence
from test_activity_boundary_seek_plan import report, four_table_report
from video_validator import validate_recording


class BoundaryContactSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'video.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=4:duration=9',
                        '-c:v', 'mpeg4', str(cls.video)], check=True, capture_output=True)
        cls.sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        cls.plan = build_boundary_seek_plan(
            four_table_report(cls.sha), recording_sha256=cls.sha,
            duration_seconds=validate_recording(cls.video)['duration_seconds'])
        cls.plan_path = cls.root / 'plan.json'
        cls.plan_path.write_text(json.dumps(cls.plan), encoding='utf-8')
        cls.evidence = cls.root / 'evidence'
        cls.manifest = export_activity_evidence(cls.video, cls.plan, cls.evidence)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sheet(self, plan=None, manifest=None):
        return build_boundary_contact_sheet(plan or self.plan, manifest or self.manifest,
                                            self.evidence)

    def test_four_tables_twelve_images(self):
        r = self.sheet()
        self.assertEqual(len(r['windows']), 4)
        self.assertEqual(r['resolved_count'], 12)
        self.assertEqual(r['unresolved_count'], 0)
        self.assertEqual({w['table_id'] for w in r['windows']}, {1, 2, 3, 4})
        self.assertTrue(all(len(w['frames']) == 3 for w in r['windows']))
        self.assertTrue(all(f['status'] == 'unverified_visual_evidence'
                            for w in r['windows'] for f in w['frames']))
        self.assertFalse(r['automatic_hand_boundaries_authorized'])
        self.assertFalse(r['ready_for_equity_or_ev'])
        self.assertFalse(r['strategic_error_established'])

    def test_provenance_and_timestamp_semantics(self):
        r = self.sheet()
        self.assertEqual(r['recording_sha256'], self.sha)
        self.assertIn('decoded_filtergraph_pts', r['timestamp_semantics'])
        for w in r['windows']:
            for f in w['frames']:
                self.assertIn('decoded_source_pts_ticks', f)
                self.assertGreaterEqual(f['decoded_source_pts_seconds'],
                                        f['requested_seek_seconds'])
                self.assertTrue(f['image'].startswith('images/table_'))

    def test_export_self_contained_packet_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            dest = Path(t) / 'packet'
            r = export_boundary_contact_sheet(self.plan_path, self.evidence, dest)
            self.assertEqual(r['resolved_count'], 12)
            self.assertEqual(len(list(dest.rglob('*.png'))), 12)
            self.assertEqual(json.loads((dest/'report.json').read_text()), r)
            html = (dest/'index.html').read_text()
            self.assertIn('Revisão offline', html)
            self.assertIn('images/table_01/', html)
            self.assertNotIn('<script', html)
            with self.assertRaises(ValueError):
                export_boundary_contact_sheet(self.plan_path, self.evidence, dest)

    def test_reject_changed_source_hash(self):
        p = copy.deepcopy(self.plan)
        p['recording_sha256'] = 'a'*64
        with self.assertRaises(ValueError):
            self.sheet(plan=p)

    def test_reject_premature_authorization(self):
        for key in ('automatic_hand_boundaries_authorized', 'automatic_clip_selection_authorized',
                    'ready_for_equity_or_ev', 'strategic_error_established'):
            with self.subTest(key=key):
                p = copy.deepcopy(self.plan)
                p[key] = True
                with self.assertRaises(ValueError):
                    self.sheet(plan=p)

    def test_reject_relabelled_seek(self):
        m = copy.deepcopy(self.manifest)
        m['frames'][0]['seek_reason'] = 'baseline_grid'
        with self.assertRaises(ValueError):
            self.sheet(manifest=m)

    def test_reject_missing_seek(self):
        m = copy.deepcopy(self.manifest)
        m['frames'].pop()
        m['resolved_count'] -= 1
        m['requested_count'] -= 1
        with self.assertRaises(ValueError):
            self.sheet(manifest=m)

    def test_reject_duplicate_seek(self):
        p = copy.deepcopy(self.plan)
        p['tables'][0]['requested_frames'].append(copy.deepcopy(p['tables'][0]['requested_frames'][0]))
        p['tables'][0]['planned_count'] += 1
        p['planned_total_frames'] += 1
        with self.assertRaises(ValueError):
            self.sheet(plan=p)

    def test_reject_orphan_window_seek(self):
        p = copy.deepcopy(self.plan)
        p['review_window_seek_associations'][0]['requested_seek_seconds'].pop()
        with self.assertRaises(ValueError):
            self.sheet(plan=p)

    def test_reject_outside_window_seek(self):
        p = copy.deepcopy(self.plan)
        p['review_window_seek_associations'][0]['candidate_interval_pts'] = [0, 1]
        with self.assertRaises(ValueError):
            self.sheet(plan=p)

    def test_reject_unsafe_image_path(self):
        m = copy.deepcopy(self.manifest)
        m['frames'][0]['image'] = '../../secrets.png'
        with self.assertRaises(ValueError):
            self.sheet(manifest=m)

    def test_reject_image_hash_tampering(self):
        m = copy.deepcopy(self.manifest)
        m['frames'][0]['sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.sheet(manifest=m)

    def test_reject_image_budget(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, 'budget'):
                export_boundary_contact_sheet(self.plan_path, self.evidence,
                                              Path(t)/'packet', max_total_png_bytes=1)

    def test_reject_boolean_limits(self):
        with self.assertRaises(ValueError):
            build_boundary_contact_sheet(
                self.plan, self.manifest, self.evidence, max_images=True)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export_boundary_contact_sheet(self.plan_path, self.evidence,
                                              Path(t)/'packet', max_total_png_bytes=True)

    def test_unresolved_seek_explicit(self):
        m = copy.deepcopy(self.manifest)
        row = m['frames'].pop()
        m['resolved_count'] -= 1
        m['unresolved_count'] += 1
        m['unresolved'].append({'table_id': row['table_id'],
                                'requested_seek_seconds': row['requested_seek_seconds'],
                                'reason': 'no_decoded_frame_within_seek_drift'})
        r = self.sheet(manifest=m)
        self.assertEqual(r['unresolved_count'], 1)
        self.assertEqual(sum(f['status'] == 'no_decoded_frame'
                             for w in r['windows'] for f in w['frames']), 1)

    def test_decoded_outside_candidate_interval_flagged(self):
        # 3 fps quantizes the final requested seek (6.25s) to a later
        # decoded frame (6.333s), outside a still-valid 4.7..6.26 window.
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'three_fps.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=3:duration=9',
                            '-c:v', 'mpeg4', str(video)], check=True, capture_output=True)
            sha = hashlib.sha256(video.read_bytes()).hexdigest()
            p = build_boundary_seek_plan(four_table_report(sha), recording_sha256=sha,
                                         duration_seconds=validate_recording(video)['duration_seconds'])
            p['review_window_seek_associations'][0]['candidate_interval_pts'] = [4.7, 6.26]
            evidence = Path(temp) / 'evidence'
            m = export_activity_evidence(video, p, evidence)
            r = build_boundary_contact_sheet(p, m, evidence)
            self.assertIn('decoded_outside_candidate_interval_review_required',
                          [f['status'] for f in r['windows'][0]['frames']])

    def test_no_mutation(self):
        p, m = copy.deepcopy(self.plan), copy.deepcopy(self.manifest)
        self.sheet()
        self.assertEqual(p, self.plan)
        self.assertEqual(m, self.manifest)


if __name__ == '__main__':
    unittest.main()
