"""Synthetic, offline-only validation of reviewed hand-to-MP4 bridge."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import offline_reviewed_boundary_clip_pipeline as bridge

VIDEO = None
_TEMP_VIDEO = None


def setUpModule():
    global VIDEO, _TEMP_VIDEO
    _TEMP_VIDEO = tempfile.TemporaryDirectory()
    VIDEO = Path(_TEMP_VIDEO.name) / 'synthetic.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                    '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=10',
                    '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    str(VIDEO)], check=True, capture_output=True)


def tearDownModule():
    _TEMP_VIDEO.cleanup()


def base():
    sha = hashlib.sha256(VIDEO.read_bytes()).hexdigest()
    hands = {'schema_version': 1, 'status': 'human_annotated_hand_boundaries',
             'recording_sha256': sha,
             'hands': [{'table_id': i, 'start_seconds': 0.2,
                        'end_seconds': 1.2} for i in range(1, 5)]}
    picks = {'schema_version': 1, 'time_basis': 'playback_seconds',
             'recording_sha256': sha,
             'selections': [{'review_id': f'r{i}', 'hand_index': i - 1,
                             'table_id': i, 'explanation': f'Reviewed table {i}',
                             'human_reviewed': True,
                             'crop': {'x': ((i - 1) % 2) * 320,
                                      'y': ((i - 1) // 2) * 180,
                                      'width': 320, 'height': 180}}
                            for i in range(1, 5)]}
    return hands, picks


class Validation(unittest.TestCase):
    def setUp(self):
        self.hands, self.picks = base()

    def check_invalid(self, *, hands=None, picks=None):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            bridge.validate_and_build(hands if hands is not None else self.hands,
                                      picks if picks is not None else self.picks,
                                      self.hands['recording_sha256'], 2.0, (640, 360))

    def test_valid_four_tables(self):
        manifest = bridge.validate_and_build(self.hands, self.picks,
                                             self.hands['recording_sha256'], 2.0, (640, 360))
        self.assertEqual(len(manifest['clips']), 4)
        self.assertEqual([c['start_seconds'] for c in manifest['clips']], [0.2] * 4)
        self.assertTrue(all(c['human_reviewed'] is True for c in manifest['clips']))

    def test_wrong_video_hash(self):
        self.picks['recording_sha256'] = 'a' * 64
        self.check_invalid()

    def test_wrong_hands_hash(self):
        self.hands['recording_sha256'] = 'a' * 64
        self.check_invalid()

    def test_wrong_time_basis(self):
        self.picks['time_basis'] = 'source_pts'
        self.check_invalid()

    def test_missing_review(self):
        self.picks['selections'][0]['human_reviewed'] = False
        self.check_invalid()

    def test_duplicate_hand_index(self):
        self.picks['selections'][1]['hand_index'] = 0
        self.check_invalid()

    def test_wrong_table(self):
        self.picks['selections'][0]['table_id'] = 2
        self.check_invalid()

    def test_outside_video(self):
        self.hands['hands'][0]['end_seconds'] = 3
        self.check_invalid()

    def test_invalid_negative_timestamp(self):
        self.hands['hands'][0]['start_seconds'] = -1
        self.check_invalid()

    def test_overlapping_same_table(self):
        self.hands['hands'][1]['table_id'] = 1
        self.check_invalid()

    def test_adjacent_same_table_allowed(self):
        self.hands['hands'][1].update(table_id=1, start_seconds=1.2, end_seconds=1.8)
        self.picks['selections'][1]['table_id'] = 1
        manifest = bridge.validate_and_build(self.hands, self.picks,
                                             self.hands['recording_sha256'], 2, (640, 360))
        self.assertEqual(len(manifest['clips']), 4)

    def test_wrong_crop(self):
        self.picks['selections'][0]['crop']['width'] = 322
        self.picks['selections'][0]['crop']['x'] = 320
        self.check_invalid()

    def test_duplicate_review_id(self):
        self.picks['selections'][1]['review_id'] = 'r1'
        self.check_invalid()

    def test_unexpected_boundary_field(self):
        self.hands['hands'][0]['verified'] = True
        self.check_invalid()

    def test_unexpected_selection_field(self):
        self.picks['selections'][0]['auto_selected'] = True
        self.check_invalid()

    def test_no_selections(self):
        self.picks['selections'] = []
        self.check_invalid()

    def test_bool_table_id(self):
        self.hands['hands'][0]['table_id'] = True
        self.check_invalid()

    def test_nan_timestamp(self):
        self.hands['hands'][0]['start_seconds'] = float('nan')
        self.check_invalid()

    def test_bad_subtitle(self):
        self.picks['selections'][0]['explanation'] = 'unsafe{value}'
        self.check_invalid()

    def test_too_long_clip(self):
        self.hands['hands'][0]['end_seconds'] = 200
        self.check_invalid()

    def test_too_many_picks(self):
        self.picks['selections'] *= 4
        self.check_invalid()

    def test_non_integer_hand_index(self):
        self.picks['selections'][0]['hand_index'] = 0.0
        self.check_invalid()

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'x.json'
            f.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):
                bridge.load(f)

    def test_json_nan_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'x.json'
            f.write_text('{"x":NaN}')
            with self.assertRaises(ValueError):
                bridge.load(f)


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        hands, picks = base()
        self.hands_path = self.root / 'hands.json'
        self.picks_path = self.root / 'picks.json'
        self.hands_path.write_text(json.dumps(hands))
        self.picks_path.write_text(json.dumps(picks))
        self.out = self.root / 'output'

    def test_real_four_mp4_exports(self):
        report = bridge.run(VIDEO, self.hands_path, self.picks_path, self.out)
        self.assertEqual(report['clip_count'], 4)
        self.assertFalse(report['human_annotations_authenticated'])
        self.assertFalse(report['equity_or_ev_verified'])
        self.assertEqual(len(list((self.out / 'clips').glob('*.mp4'))), 4)
        for clip in (self.out / 'clips').glob('*.mp4'):
            seconds = bridge.exporter.duration_seconds(clip)
            self.assertAlmostEqual(seconds, 1.0, delta=0.3)
        manifest = json.loads((self.out / 'review_manifest.json').read_text())
        self.assertEqual([c['table_id'] for c in manifest['clips']], [1, 2, 3, 4])
        self.assertEqual(json.loads((self.out / 'pipeline_report.json').read_text()), report)

    def test_output_exists_no_overwrite(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):
            bridge.run(VIDEO, self.hands_path, self.picks_path, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_input_hash_mismatch_no_publication(self):
        obj = json.loads(self.hands_path.read_text())
        obj['recording_sha256'] = '0' * 64
        self.hands_path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            bridge.run(VIDEO, self.hands_path, self.picks_path, self.out)
        self.assertFalse(self.out.exists())

    def test_missing_ffmpeg_no_publication(self):
        with self.assertRaises(ValueError):
            bridge.run(VIDEO, self.hands_path, self.picks_path, self.out,
                       ffmpeg='__nonexistent_ffmpeg__')
        self.assertFalse(self.out.exists())

    def test_symlink_input_rejected(self):
        link = self.root / 'linked.json'
        link.symlink_to(self.hands_path)
        with self.assertRaises(ValueError):
            bridge.run(VIDEO, link, self.picks_path, self.out)
        self.assertFalse(self.out.exists())

    def test_cli_relative_recording(self):
        obj = json.loads(self.picks_path.read_text())
        obj['selections'] = obj['selections'][:1]
        self.picks_path.write_text(json.dumps(obj))
        result = subprocess.run([sys.executable, str(Path(bridge.__file__)), VIDEO.name,
                                 str(self.hands_path), str(self.picks_path), str(self.out)],
                                cwd=VIDEO.parent, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['clips'], 1)
        self.assertEqual(len(list((self.out / 'clips').glob('*.mp4'))), 1)

    def test_cli_one_clip(self):
        obj = json.loads(self.picks_path.read_text())
        obj['selections'] = obj['selections'][:1]
        self.picks_path.write_text(json.dumps(obj))
        result = subprocess.run([sys.executable, str(Path(bridge.__file__)), str(VIDEO),
                                 str(self.hands_path), str(self.picks_path), str(self.out)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['clips'], 1)
        self.assertEqual(len(list((self.out / 'clips').glob('*.mp4'))), 1)


if __name__ == '__main__':
    unittest.main()
