"""Synthetic tests for OCR boundary navigation evidence (no verified hands)."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from activity_ocr_boundary_triage import build_ocr_boundary_triage
from activity_ocr_boundary_visual_evidence import (
    build_boundary_visual_plan, export_boundary_visual_evidence)
from test_activity_ocr_boundary_triage import change, report, A, B


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BoundaryVisualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=5:d=4',
                        '-vf', 'drawbox=x=0:y=0:w=160:h=120:color=red:t=fill,'
                               'drawbox=x=160:y=0:w=160:h=120:color=blue:t=fill,'
                               'drawbox=x=0:y=120:w=160:h=120:color=green:t=fill,'
                               'drawbox=x=160:y=120:w=160:h=120:color=yellow:t=fill',
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmpcase = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpcase.cleanup)
        self.root = Path(self.tmpcase.name)
        self.temporal = report(*(change('hero_cards', A, B, table=i) for i in range(1, 5)))
        self.temporal['recording_sha256'] = digest(self.video)
        self.temporal_path = self.root / 'temporal.json'
        self.temporal_path.write_text(json.dumps(self.temporal))
        self.boundary = build_ocr_boundary_triage(self.temporal, source_sha256=digest(self.temporal_path))
        self.boundary_path = self.root / 'boundary.json'
        self.boundary_path.write_text(json.dumps(self.boundary))
        self.regions = {str(i): {'x': ((i - 1) % 2) * 160,
                                 'y': ((i - 1) // 2) * 120,
                                 'width': 160, 'height': 120} for i in range(1, 5)}

    def plan(self, **kwargs):
        return build_boundary_visual_plan(self.video, self.temporal, self.boundary,
                                          temporal_sha256=digest(self.temporal_path), **kwargs)

    def test_four_tables_have_separate_frame_ids(self):
        plan = self.plan(samples_per_window=2)
        self.assertEqual(plan['counts']['review_windows'], 4)
        self.assertEqual(plan['counts']['frames_planned'], 8)
        self.assertEqual({r['table_id'] for r in plan['frames']}, {1, 2, 3, 4})
        self.assertEqual(len({r['filename'] for r in plan['frames']}), 8)
        self.assertTrue(all(r['decoded_pts_seconds'] is None for r in plan['frames']))
        for key in ('hand_boundaries_verified', 'cards_or_actions_verified',
                    'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                    'strategic_error_established'):
            self.assertIs(plan[key], False)

    def test_budget_is_explicit_not_silent(self):
        plan = self.plan(max_frames=2, samples_per_window=3)
        self.assertEqual(plan['counts']['frames_planned'], 2)
        self.assertEqual(plan['counts']['skipped_or_partial_windows'], 4)
        self.assertEqual(len(plan['window_associations']), 1)

    def test_rejects_forged_boundary(self):
        altered = copy.deepcopy(self.boundary)
        altered['review_windows'][0]['priority'] = 'review_first'
        with self.assertRaises(ValueError):
            build_boundary_visual_plan(self.video, self.temporal, altered,
                                       temporal_sha256=digest(self.temporal_path))

    def test_rejects_recording_hash_mismatch(self):
        altered = copy.deepcopy(self.temporal)
        altered['recording_sha256'] = 'a' * 64
        boundary = build_ocr_boundary_triage(altered, source_sha256=digest(self.temporal_path))
        with self.assertRaises(ValueError):
            build_boundary_visual_plan(self.video, altered, boundary,
                                       temporal_sha256=digest(self.temporal_path))

    def test_rejects_invalid_regions_and_boolean_budget(self):
        for regions in ({'1': {'x': 0, 'y': 0, 'width': 999, 'height': 100}},
                        {'1': {'x': True, 'y': 0, 'width': 100, 'height': 100}},
                        {'5': {'x': 0, 'y': 0, 'width': 100, 'height': 100}}):
            with self.subTest(regions=regions), self.assertRaises(ValueError):
                self.plan(table_regions=regions)
        with self.assertRaises(ValueError):
            self.plan(max_frames=True)

    def test_ffmpeg_exports_table_crops_with_sha_and_no_pts_claim(self):
        region_path = self.root / 'regions.json'
        region_path.write_text(json.dumps(self.regions))
        output = self.root / 'evidence'
        result = export_boundary_visual_evidence(
            self.video, self.temporal_path, self.boundary_path, output,
            samples_per_window=1, regions_json=region_path)
        self.assertEqual(result['counts']['frames_planned'], 4)
        self.assertTrue(result['table_regions_manually_supplied'])
        self.assertEqual(len(list(output.glob('*.png'))), 4)
        for row in result['frames']:
            self.assertEqual(row['sha256'], digest(output / row['filename']))
            self.assertEqual(row['status'], 'navigation_png_extracted_not_pts_audited')
            self.assertIsNone(row['decoded_pts_seconds'])
            self.assertFalse(row['decoded_pts_verified'])
        self.assertEqual(json.loads((output / 'boundary_visual_evidence.json').read_text()), result)
        with self.assertRaises(ValueError):
            export_boundary_visual_evidence(self.video, self.temporal_path,
                                            self.boundary_path, output)

    def test_rejects_tampered_temporal_and_symlink(self):
        self.temporal_path.write_text(self.temporal_path.read_text() + ' ')
        with self.assertRaises(ValueError):
            export_boundary_visual_evidence(self.video, self.temporal_path,
                                            self.boundary_path, self.root / 'bad')
        link = self.root / 'video-link.mp4'
        link.symlink_to(self.video)
        with self.assertRaises(ValueError):
            export_boundary_visual_evidence(link, self.temporal_path,
                                            self.boundary_path, self.root / 'bad')

    def test_outside_duration_skipped(self):
        temporal = report(change('hero_cards', A, B, start=5, end=6))
        temporal['recording_sha256'] = digest(self.video)
        path = self.root / 'future.json'
        path.write_text(json.dumps(temporal))
        boundary = build_ocr_boundary_triage(temporal, source_sha256=digest(path))
        result = build_boundary_visual_plan(self.video, temporal, boundary,
                                            temporal_sha256=digest(path))
        self.assertEqual(result['counts']['frames_planned'], 0)
        self.assertEqual(result['skipped_windows'][0]['reason'], 'window_outside_recording_duration')


if __name__ == '__main__':
    unittest.main()
