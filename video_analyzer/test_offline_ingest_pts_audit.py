"""Synthetic FFmpeg regression for independent VFR-aware offline ingest audit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_ingest_pts_audit import audit, main, materially_variable_intervals


def cmd(args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=60)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg/FFprobe required')
class SyntheticVfrFourTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='plo_vfr_audit_')
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'synthetic_vfr.mp4'
        # Frame interval changes from 0.1 s to 0.2 s. Four distinguishable quadrants.
        boxes = ','.join(f'drawbox=x={x}:y={y}:w=160:h=120:color={c}:t=fill'
                         for x, y, c in [(0, 0, 'red'), (160, 0, 'green'),
                                         (0, 120, 'blue'), (160, 120, 'yellow')])
        cmd(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
             '-i', 'color=c=black:s=320x240:r=10:d=1',
             '-vf', boxes + ",setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
             '-fps_mode', 'vfr', '-c:v', 'mpeg4', '-q:v', '4', str(cls.video)])
        result = cmd(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                      '-show_entries', 'frame=best_effort_timestamp_time',
                      '-of', 'csv=p=0', str(cls.video)])
        cls.pts = [float(x) for x in result.stdout.decode().splitlines() if x.strip()]
        assert len(cls.pts) >= 9
        assert len(set(round(b - a, 4) for a, b in zip(cls.pts, cls.pts[1:]))) > 1
        cls.base = cls.root / 'base'
        cls.base.mkdir()
        regions = [{'table_id': i, 'x': x, 'y': y, 'width': 160, 'height': 120}
                   for i, (x, y) in enumerate([(0, 0), (160, 0), (0, 120),
                                                (160, 120)], 1)]
        samples = []
        for i, region in enumerate(regions, 1):
            for j, frame_index in enumerate((2, 7)):
                name = f'table_{i:02d}_sample_{j:03d}.jpg'
                crop = f"crop=160:120:{region['x']}:{region['y']}"
                cmd(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(cls.video),
                     '-vf', f'select=eq(n\\,{frame_index}),{crop}',
                     '-frames:v', '1', '-q:v', '3', '-y', str(cls.base / name)])
                samples.append({'table_id': i, 'timestamp_seconds':
                                round(cls.pts[frame_index] - .025, 3),
                                'actual_frame_timestamp_seconds': cls.pts[frame_index],
                                'file': name, 'sha256': sha(cls.base / name)})
        cls.manifest = {
            'schema_version': 1,
            'analysis_status': 'offline_sampled_video_preflight_no_ocr',
            'source_sha256': sha(cls.video),
            'source_size_bytes': cls.video.stat().st_size,
            'media': {'width': 320, 'height': 240},
            'regions': regions, 'samples': samples,
            'video_evidence_interpreted': False, 'hands_reconstructed': False,
            'equity_ev_computed': False}
        (cls.base / 'manifest.json').write_text(json.dumps(cls.manifest))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plo_vfr_case_')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.ingest = self.folder / 'ingest'
        shutil.copytree(self.base, self.ingest)
        self.data = json.loads((self.ingest / 'manifest.json').read_text())

    def save(self):
        (self.ingest / 'manifest.json').write_text(json.dumps(self.data))

    def test_timestamp_quantization_not_mislabeled_vfr(self):
        self.assertFalse(materially_variable_intervals([0, .033, .067, .100, .133, .167]))
        self.assertTrue(materially_variable_intervals([0, .1, .2, .4, .6]))

    def test_four_tables_vfr_pts_and_jpeg_sha(self):
        report = audit(self.video, self.ingest)
        self.assertEqual(report['table_count'], 4)
        self.assertEqual(report['sample_count'], 8)
        self.assertTrue(report['variable_frame_intervals_observed'])
        self.assertEqual(report['source_decoded_frame_count'], len(self.pts))
        self.assertFalse(report['equity_ev_authorized'])
        self.assertTrue(all(s['crop_sha256_verified'] for s in report['verified_samples']))

    def test_cli_writes_new_report_and_rejects_overwrite(self):
        output = self.folder / 'report.json'
        self.assertEqual(main([str(self.video), str(self.ingest), str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())['sample_count'], 8)
        with self.assertRaises(ValueError):
            main([str(self.video), str(self.ingest), str(output)])

    def test_wrong_decoded_pts_is_rejected(self):
        self.data['samples'][0]['actual_frame_timestamp_seconds'] += .06
        self.save()
        with self.assertRaisesRegex(ValueError, 'decoded PTS absent'):
            audit(self.video, self.ingest)

    def test_wrong_source_hash_is_rejected(self):
        self.data['source_sha256'] = '0' * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'source hash'):
            audit(self.video, self.ingest)

    def test_modified_crop_is_rejected(self):
        crop = self.ingest / self.data['samples'][0]['file']
        crop.write_bytes(crop.read_bytes() + b'altered')
        with self.assertRaisesRegex(ValueError, 'adulterated'):
            audit(self.video, self.ingest)

    def test_missing_table_is_rejected(self):
        self.data['samples'] = [s for s in self.data['samples'] if s['table_id'] != 4]
        self.save()
        with self.assertRaisesRegex(ValueError, 'missing samples'):
            audit(self.video, self.ingest)

    def test_path_traversal_is_rejected(self):
        self.data['samples'][0]['file'] = '../outside.jpg'
        self.save()
        with self.assertRaisesRegex(ValueError, 'unsafe/duplicate'):
            audit(self.video, self.ingest)

    def test_duplicate_sample_is_rejected(self):
        self.data['samples'][1]['file'] = self.data['samples'][0]['file']
        self.save()
        with self.assertRaisesRegex(ValueError, 'unsafe/duplicate'):
            audit(self.video, self.ingest)

    def test_wrong_crop_geometry_is_rejected(self):
        self.data['regions'][0]['width'] = 158
        self.save()
        with self.assertRaisesRegex(ValueError, 'incorrect crop'):
            audit(self.video, self.ingest)

    def test_uncertified_manifest_is_rejected(self):
        self.data['equity_ev_computed'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'not an unverified'):
            audit(self.video, self.ingest)

    def test_symlink_crop_is_rejected(self):
        crop = self.ingest / self.data['samples'][0]['file']
        replacement = self.folder / 'replacement.jpg'
        shutil.copyfile(crop, replacement)
        crop.unlink()
        crop.symlink_to(replacement)
        with self.assertRaisesRegex(ValueError, 'adulterated'):
            audit(self.video, self.ingest)

    def test_duplicate_json_key_is_rejected(self):
        p = self.ingest / 'manifest.json'
        p.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            audit(self.video, self.ingest)


if __name__ == '__main__':
    unittest.main()
