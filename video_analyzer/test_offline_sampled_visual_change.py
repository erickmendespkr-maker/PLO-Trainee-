"""Synthetic-only tests: change signals are never asserted to be poker hands."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_video_ingest_probe import build
from offline_sampled_visual_change import analyze, compare_frames, SIDE


class VisualChangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.base = Path(cls.root.name)
        cls.video = cls.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=gray:s=640x180:r=1', '-t', '6',
                        '-vf', "drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='gte(t,2)'",
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True)
        cls.regions = cls.base / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180},
            {'table_id': 2, 'x': 320, 'y': 0, 'width': 320, 'height': 180}]}))
        cls.ingest = cls.base / 'ingest'
        build(cls.video, cls.regions, cls.ingest)

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base_test = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_detects_only_changed_table(self):
        result = analyze(self.ingest, self.base_test / 'report')
        self.assertEqual(result['table_count'], 2)
        self.assertEqual(result['sample_count'], 6)
        self.assertEqual({x['table_id'] for x in result['candidate_intervals']}, {1})
        self.assertTrue(all(x['hand_boundary_confidence'] is None for x in result['candidate_intervals']))
        self.assertFalse(result['hands_reconstructed'])
        self.assertEqual(json.loads((self.base_test / 'report' / 'visual_changes.json').read_text()), result)

    def test_changed_interval_is_bounded_by_actual_pts(self):
        result = analyze(self.ingest, self.base_test / 'report')
        for event in result['candidate_intervals']:
            self.assertLess(event['earliest_possible_change_seconds'], event['latest_possible_change_seconds'])
            self.assertGreater(event['mean_absolute_grayscale_difference'], 0.12)
            self.assertGreater(event['changed_pixel_fraction'], 0.2)

    def test_sparse_evidence_is_flagged(self):
        result = analyze(self.ingest, self.base_test / 'report', max_gap_seconds=1)
        self.assertTrue(all(x['sparse_evidence'] for x in result['candidate_intervals']))

    def test_high_threshold_suppresses_candidates(self):
        result = analyze(self.ingest, self.base_test / 'report', threshold=0.9)
        self.assertEqual(result['candidate_intervals'], [])

    def test_bad_parameters_no_output(self):
        for i, kwargs in enumerate(({'threshold': 0}, {'threshold': True},
                                    {'min_coverage': -0.1}, {'max_gap_seconds': 0},
                                    {'threshold': float('nan')})):
            output = self.base_test / f'bad_{i}'
            with self.assertRaises(ValueError):
                analyze(self.ingest, output, **kwargs)
            self.assertFalse(output.exists())

    def test_output_must_be_new(self):
        output = self.base_test / 'already'
        output.mkdir()
        with self.assertRaises(ValueError):
            analyze(self.ingest, output)

    def test_modified_jpeg_is_rejected(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        jpeg = next(copied.glob('*.jpg'))
        jpeg.write_bytes(jpeg.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'modified'):
            analyze(copied, self.base_test / 'report')
        self.assertFalse((self.base_test / 'report').exists())

    def test_missing_jpeg_is_rejected(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        next(copied.glob('*.jpg')).unlink()
        with self.assertRaises(ValueError):
            analyze(copied, self.base_test / 'report')

    def test_path_traversal_is_rejected(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        manifest = json.loads((copied / 'manifest.json').read_text())
        manifest['samples'][0]['file'] = '../other.jpg'
        (copied / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            analyze(copied, self.base_test / 'report')

    def test_duplicate_json_key_is_rejected(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        path = copied / 'manifest.json'
        path.write_text(path.read_text().replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'))
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            analyze(copied, self.base_test / 'report')

    def test_symlink_sample_is_rejected(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        jpeg = next(copied.glob('*.jpg'))
        backup = self.base_test / 'original.jpg'
        shutil.copy2(jpeg, backup)
        jpeg.unlink()
        try:
            jpeg.symlink_to(backup)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unsupported')
        with self.assertRaises(ValueError):
            analyze(copied, self.base_test / 'report')

    def test_duplicate_pts_is_diagnostic_not_hand(self):
        copied = self.base_test / 'copied'
        shutil.copytree(self.ingest, copied)
        path = copied / 'manifest.json'
        manifest = json.loads(path.read_text())
        first = next(s for s in manifest['samples'] if s['table_id'] == 1)
        last = next(s for s in manifest['samples'] if s['table_id'] == 1 and s['file'] != first['file'])
        last['actual_frame_timestamp_seconds'] = first['actual_frame_timestamp_seconds']
        path.write_text(json.dumps(manifest))
        result = analyze(copied, self.base_test / 'report')
        self.assertTrue(any(x['reason'] == 'duplicate_or_nonincreasing_decoded_pts' for x in result['diagnostics']))

    def test_compare_frames_exact(self):
        a = bytes([0]) * (SIDE * SIDE)
        b = bytes([255]) * (SIDE * SIDE)
        self.assertEqual(compare_frames(a, a), (0, 0))
        self.assertEqual(compare_frames(a, b), (1, 1))
        with self.assertRaises(ValueError):
            compare_frames(a, b[:-1])


if __name__ == '__main__':
    unittest.main()
