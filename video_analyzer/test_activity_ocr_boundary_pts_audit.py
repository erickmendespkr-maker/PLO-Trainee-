"""Synthetic tests for decoded PTS auditing of unverified OCR boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from activity_ocr_boundary_triage import build_ocr_boundary_triage
from activity_ocr_boundary_visual_evidence import export_boundary_visual_evidence
from activity_ocr_boundary_pts_audit import audit_ocr_boundary_pts
from test_activity_ocr_boundary_triage import change, report, A, B


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BoundaryPTSAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp.name) / 'video.mp4'
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
        temporal = report(*(change('hero_cards', A, B, table=i) for i in range(1, 5)))
        temporal['recording_sha256'] = sha(self.video)
        self.temporal = self.root / 'temporal.json'
        self.temporal.write_text(json.dumps(temporal))
        boundary = build_ocr_boundary_triage(temporal, source_sha256=sha(self.temporal))
        self.boundary = self.root / 'boundary.json'
        self.boundary.write_text(json.dumps(boundary))
        self.regions = self.root / 'regions.json'
        self.regions.write_text(json.dumps({
            str(i): {'x': ((i-1) % 2) * 160, 'y': ((i-1) // 2) * 120,
                     'width': 160, 'height': 120} for i in range(1, 5)}))
        self.evidence = self.root / 'evidence'
        export_boundary_visual_evidence(self.video, self.temporal, self.boundary,
                                        self.evidence, regions_json=self.regions,
                                        samples_per_window=1)
        self.output = self.root / 'audit'

    def run_audit(self, **kwargs):
        return audit_ocr_boundary_pts(self.video, self.temporal, self.boundary,
                                      self.evidence, self.output, regions_json=self.regions,
                                      **kwargs)

    def test_four_tables_byte_identical_and_pts(self):
        result = self.run_audit()
        self.assertEqual(result['counts'], {'frames_checked': 4,
                         'byte_identical_decodes': 4, 'unverified_pts': 0})
        self.assertEqual({r['table_id'] for r in result['frames']}, {1, 2, 3, 4})
        self.assertTrue(all(r['decoded_pts_seconds'] is not None for r in result['frames']))
        self.assertTrue(all(r['png_bytes_match'] for r in result['frames']))
        self.assertEqual(json.loads((self.output / 'boundary_pts_audit.json').read_text()), result)
        for flag in ('hand_boundaries_verified', 'cards_or_actions_verified',
                     'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                     'strategic_error_established'):
            self.assertIs(result[flag], False)
        self.assertTrue(result['requires_manual_review'])

    def test_three_samples_and_budget_limited(self):
        for samples, budget, expected in ((2, 60, 8), (3, 60, 12), (3, 2, 2)):
            with self.subTest(samples=samples, budget=budget):
                other = self.root / f'evidence_{samples}_{budget}'
                out = self.root / f'audit_{samples}_{budget}'
                export_boundary_visual_evidence(self.video, self.temporal, self.boundary,
                                                other, regions_json=self.regions,
                                                samples_per_window=samples, max_frames=budget)
                result = audit_ocr_boundary_pts(self.video, self.temporal, self.boundary,
                                                other, out, regions_json=self.regions)
                self.assertEqual(result['counts']['frames_checked'], expected)
                self.assertEqual(result['counts']['byte_identical_decodes'], expected)

    def test_rejects_overwrite(self):
        self.run_audit()
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_rejects_tampered_png(self):
        image = next(self.evidence.glob('*.png'))
        image.write_bytes(image.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.run_audit()
        self.assertFalse(self.output.exists())

    def test_rejects_forged_verified_pts(self):
        path = self.evidence / 'boundary_visual_evidence.json'
        manifest = json.loads(path.read_text())
        manifest['frames'][0]['decoded_pts_verified'] = True
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_rejects_forged_seek_or_table(self):
        path = self.evidence / 'boundary_visual_evidence.json'
        manifest = json.loads(path.read_text())
        manifest['frames'][0]['requested_seek_seconds'] = 2.5
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_rejects_region_mismatch(self):
        self.regions.write_text(json.dumps({'1': {'x': 0, 'y': 0, 'width': 100, 'height': 100}}))
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_rejects_forged_boundary(self):
        data = json.loads(self.boundary.read_text())
        data['review_windows'][0]['priority'] = 'review_first'
        self.boundary.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_rejects_symlink_and_output_inside_evidence(self):
        link = self.root / 'linked_evidence'
        link.symlink_to(self.evidence, target_is_directory=True)
        with self.assertRaises(ValueError):
            audit_ocr_boundary_pts(self.video, self.temporal, self.boundary,
                                   link, self.output, regions_json=self.regions)
        with self.assertRaises(ValueError):
            audit_ocr_boundary_pts(self.video, self.temporal, self.boundary,
                                   self.evidence, self.evidence / 'nested', regions_json=self.regions)

    def test_rejects_extra_png(self):
        (self.evidence / 'untracked.png').write_bytes(b'junk')
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            self.run_audit()

    def test_no_regions_full_frames(self):
        # Recreate evidence without a crop profile.
        new_evidence = self.root / 'full_frames'
        export_boundary_visual_evidence(self.video, self.temporal, self.boundary,
                                        new_evidence, samples_per_window=1)
        result = audit_ocr_boundary_pts(self.video, self.temporal, self.boundary,
                                        new_evidence, self.output)
        self.assertEqual(result['counts']['byte_identical_decodes'], 4)

    def test_png_mismatch_does_not_assert_pts(self):
        # Mock the re-decoder only after the original input has been checked.
        original = subprocess.run
        def substitute(cmd, *args, **kwargs):
            result = original(cmd, *args, **kwargs)
            if isinstance(cmd, list) and cmd and cmd[0] == 'ffmpeg' and '-copyts' in cmd:
                png = Path(cmd[-1])
                png.write_bytes(png.read_bytes() + b'not-byte-identical')
            return result
        with patch('activity_ocr_boundary_pts_audit.subprocess.run', side_effect=substitute):
            result = self.run_audit()
        self.assertEqual(result['counts']['unverified_pts'], 4)
        self.assertTrue(all(r['decoded_pts_seconds'] is None for r in result['frames']))


if __name__ == '__main__':
    unittest.main()
