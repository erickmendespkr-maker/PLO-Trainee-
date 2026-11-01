"""Synthetic four-table VFR tests for source-to-ROI pixel comparison."""
import json
import subprocess
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from offline_ingest_roi_pixel_audit import (verify, main, frame_index,
                                            mean_rgb_error, decode_frame)
from offline_ingest_pts_audit import audit, digest
from PIL import Image


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and FFprobe required')
class PixelAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_roi_fixture_')
        cls.demo = Path(cls.fixture.name)
        cls.video = cls.demo / 'vfr_four_tables.mp4'
        boxes = ','.join(f'drawbox=x={x}:y={y}:w=160:h=120:color={c}:t=fill'
                         for x, y, c in [(0, 0, 'red'), (160, 0, 'green'),
                                         (0, 120, 'blue'), (160, 120, 'yellow')])
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=10:d=1',
                        '-vf', boxes + ",setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
                        '-fps_mode', 'vfr', '-c:v', 'mpeg4', '-q:v', '4',
                        str(cls.video)], check=True, capture_output=True, timeout=30)
        raw = subprocess.check_output(['ffprobe', '-v', 'error',
                                       '-select_streams', 'v:0',
                                       '-show_entries', 'frame=best_effort_timestamp_time',
                                       '-of', 'csv=p=0', str(cls.video)], timeout=30)
        pts = [float(v) for v in raw.decode().splitlines() if v.strip()]
        cls.base = cls.demo / 'ingest'
        cls.base.mkdir()
        regions = [{'table_id': i, 'x': x, 'y': y, 'width': 160, 'height': 120}
                   for i, (x, y) in enumerate([(0, 0), (160, 0), (0, 120),
                                                (160, 120)], 1)]
        samples = []
        for region in regions:
            for j, index in enumerate((2, 7)):
                name = f"table_{region['table_id']:02d}_sample_{j:03d}.jpg"
                crop = f"crop=160:120:{region['x']}:{region['y']}"
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel',
                                'error', '-i', str(cls.video),
                                '-vf', f'select=eq(n\\,{index}),{crop}',
                                '-frames:v', '1', '-q:v', '3',
                                str(cls.base / name)], check=True,
                               capture_output=True, timeout=30)
                samples.append({'table_id': region['table_id'],
                                'timestamp_seconds': round(pts[index] - .025, 3),
                                'actual_frame_timestamp_seconds': pts[index],
                                'file': name, 'sha256': digest(cls.base / name)})
        manifest = {'schema_version': 1,
                    'analysis_status': 'offline_sampled_video_preflight_no_ocr',
                    'source_sha256': digest(cls.video),
                    'source_size_bytes': cls.video.stat().st_size,
                    'media': {'width': 320, 'height': 240},
                    'regions': regions, 'samples': samples,
                    'video_evidence_interpreted': False,
                    'hands_reconstructed': False, 'equity_ev_computed': False}
        (cls.base / 'manifest.json').write_text(json.dumps(manifest))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ingest = self.root / 'ingest'
        shutil.copytree(self.base, self.ingest)
        self.manifest_path = self.ingest / 'manifest.json'
        self.manifest = json.loads(self.manifest_path.read_text())

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def test_four_tables_two_vfr_frames_per_table(self):
        report = verify(self.video, self.ingest)
        self.assertEqual(report['tables'], 4)
        self.assertEqual(report['samples_checked'], 8)
        self.assertEqual(report['unique_source_frames_decoded'], 2)
        self.assertFalse(report['equity_ev_authorized'])
        self.assertTrue(all(x['visual_roi_match_within_tolerance'] for x in report['results']))

    def test_replaced_crop_with_updated_sha_passes_pts_audit_but_fails_pixels(self):
        a, b = self.manifest['samples'][0], self.manifest['samples'][2]
        self.assertNotEqual(a['table_id'], b['table_id'])
        target = self.ingest / a['file']
        target.write_bytes((self.ingest / b['file']).read_bytes())
        a['sha256'] = digest(target)
        self.save()
        self.assertEqual(audit(self.video, self.ingest)['sample_count'], 8)
        with self.assertRaisesRegex(ValueError, 'ROI pixel mismatch'):
            verify(self.video, self.ingest)

    def test_valid_cli_output_and_no_overwrite(self):
        out = self.root / 'roi.json'
        self.assertEqual(main([str(self.video), str(self.ingest), str(out)]), 0)
        self.assertEqual(json.loads(out.read_text())['samples_checked'], 8)
        with self.assertRaisesRegex(ValueError, 'new JSON'):
            main([str(self.video), str(self.ingest), str(out)])

    def test_invalid_pts_rejected(self):
        self.manifest['samples'][0]['actual_frame_timestamp_seconds'] += 0.08
        self.save()
        with self.assertRaises(ValueError):
            verify(self.video, self.ingest)

    def test_missing_crop_rejected(self):
        (self.ingest / self.manifest['samples'][0]['file']).unlink()
        with self.assertRaises(ValueError):
            verify(self.video, self.ingest)

    def test_no_report_on_error(self):
        self.manifest['source_sha256'] = '0' * 64
        self.save()
        out = self.root / 'bad.json'
        with self.assertRaises(ValueError):
            main([str(self.video), str(self.ingest), str(out)])
        self.assertFalse(out.exists())

    def test_decode_frame_rejects_invalid_index(self):
        for bad in (-1, True, 250000, 0.2):
            with self.assertRaises(ValueError):
                decode_frame(self.video, bad)

    def test_frame_index_tolerance(self):
        self.assertEqual(frame_index([0., .1, .3], .1001), 1)
        with self.assertRaises(ValueError):
            frame_index([0., .1, .3], .12)

    def test_mean_error_black_white(self):
        self.assertEqual(mean_rgb_error(Image.new('RGB',(4,4),'black'),
                                        Image.new('RGB',(4,4),'white')), 255)

    def test_ffmpeg_failure_rejected(self):
        with patch('offline_ingest_roi_pixel_audit.subprocess.run', side_effect=OSError):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                decode_frame(self.video, 0)

    def test_manifest_false_authorization_rejected(self):
        self.manifest['equity_ev_computed'] = True
        self.save()
        with self.assertRaises(ValueError):
            verify(self.video, self.ingest)


if __name__ == '__main__':
    unittest.main()
