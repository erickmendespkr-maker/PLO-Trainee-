"""Synthetic end-to-end and adversarial tests of one-pass ROI pixel audit."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ingest_roi_batch_pixel_audit import (decode_selected_frames, verify)
from offline_ingest_roi_pixel_audit import verify as verify_legacy
from offline_ingest_pts_audit import audit, digest
from offline_video_ingest_probe import build
from offline_ingest_audited_pipeline import run


class ParameterTests(unittest.TestCase):
    def test_reject_indices(self):
        for bad in ([], [True], [1, 1], [2, 1], [-1], [250000],
                    list(range(65)), [1.0]):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                list(decode_selected_frames('none.mp4', bad, (320, 240)))

    def test_reject_geometry(self):
        for size in ((0, 240), (3842, 2160), (320, True),
                     (320,), (320, 240, 1), (3840, 2161)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                list(decode_selected_frames('none.mp4', [0], size))

    def test_missing_ffmpeg_does_not_leave_result(self):
        with patch('offline_ingest_roi_batch_pixel_audit.subprocess.run',
                   side_effect=OSError('not found')):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                list(decode_selected_frames('none.mp4', [0], (320, 240)))

    def test_failed_ffmpeg_rejected(self):
        with patch('offline_ingest_roi_batch_pixel_audit.subprocess.run') as run_mock:
            run_mock.return_value.returncode = 1
            run_mock.return_value.stderr = b'bad input'
            with self.assertRaisesRegex(ValueError, 'bad input'):
                list(decode_selected_frames('none.mp4', [0], (320, 240)))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg/FFprobe required')
class BatchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_batch_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'four_tables.mp4'
        boxes = ','.join(f'drawbox=x={x}:y={y}:w=160:h=120:color={c}:t=fill'
                         for x, y, c in [(0, 0, 'red'), (160, 0, 'green'),
                                         (0, 120, 'blue'), (160, 120, 'yellow')])
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=10:d=2',
                        '-vf', boxes + ",setpts='if(lt(N,10),N,2*N-10)/(10*TB)'",
                        '-fps_mode', 'vfr', '-c:v', 'mpeg4', '-q:v', '4',
                        str(cls.video)], check=True, capture_output=True, timeout=30)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': i, 'x': x, 'y': y, 'width': 160, 'height': 120}
            for i, (x, y) in enumerate([(0, 0), (160, 0),
                                        (0, 120), (160, 120)], 1)]}))
        cls.ingest = cls.root / 'ingest'
        build(cls.video, cls.regions, cls.ingest)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def test_same_results_as_legacy_pixel_auditor(self):
        old = verify_legacy(self.video, self.ingest)
        new = verify(self.video, self.ingest)
        self.assertEqual(new['results'], old['results'])
        self.assertEqual(new['unique_source_frames_decoded'],
                         old['unique_source_frames_decoded'])
        self.assertEqual(new['ffmpeg_decode_passes'], 1)
        self.assertFalse(new['equity_ev_authorized'])

    def test_batch_frames_are_selected_by_exact_indices(self):
        from offline_ingest_pts_audit import decoded_pts
        pts = decoded_pts(self.video)
        chosen = [0, len(pts) // 2, len(pts) - 1]
        output = list(decode_selected_frames(self.video, chosen, (320, 240)))
        self.assertEqual([i for i, _ in output], chosen)
        self.assertEqual([im.size for _, im in output], [(320, 240)] * 3)

    def test_frame_count_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, 'frame count mismatch'):
            list(decode_selected_frames(self.video, [0, 200], (320, 240)))

    def test_geometry_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, 'geometry mismatch'):
            list(decode_selected_frames(self.video, [0], (160, 120)))

    def test_one_ffmpeg_decode_for_multiple_source_frames(self):
        original = subprocess.run
        calls = []
        def track(args, **kwargs):
            calls.append(args)
            return original(args, **kwargs)
        with patch('offline_ingest_roi_batch_pixel_audit.subprocess.run', side_effect=track):
            report = verify(self.video, self.ingest)
        self.assertEqual(len([args for args in calls if args[0] == 'ffmpeg']), 1)
        self.assertEqual(report['ffmpeg_decode_passes'], 1)
        self.assertGreater(report['unique_source_frames_decoded'], 1)

    def test_replaced_crop_even_with_updated_hash_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'ingest'
            shutil.copytree(self.ingest, folder)
            manifest_path = folder / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            a, b = manifest['samples'][0], manifest['samples'][3]
            self.assertNotEqual(a['table_id'], b['table_id'])
            target = folder / a['file']
            target.write_bytes((folder / b['file']).read_bytes())
            a['sha256'] = digest(target)
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(audit(self.video, folder)['sample_count'], 12)
            with self.assertRaisesRegex(ValueError, 'ROI pixel mismatch'):
                verify(self.video, folder)

    def test_integrated_pipeline_reports_batch_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'complete'
            result = run(self.video, self.regions, output, pixel_checks=8)
            self.assertEqual(result['pixel_ffmpeg_decode_passes'], 1)
            self.assertIn('single_ffmpeg', result['pixel_decoder_strategy'])
            self.assertEqual(result['total_crops_pts_hash_audited'], 12)
            self.assertEqual(result['crops_pixel_checked'], 8)
            self.assertFalse(result['equity_ev_authorized'])

    def test_pipeline_rollback_on_batch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'failed'
            with patch('offline_ingest_audited_pipeline.verify',
                       side_effect=ValueError('batch failure')):
                with self.assertRaisesRegex(ValueError, 'batch failure'):
                    run(self.video, self.regions, output, pixel_checks=4)
            self.assertFalse(output.exists())

    def test_source_unchanged(self):
        before = digest(self.video)
        verify(self.video, self.ingest)
        self.assertEqual(before, digest(self.video))


if __name__ == '__main__':
    unittest.main()
