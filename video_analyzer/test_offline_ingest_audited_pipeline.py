"""Synthetic tests invoking the exact repository ingest and both audit modules."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ingest_audited_pipeline import run, choose_spotcheck, main
from offline_ingest_pts_audit import audit
from offline_ingest_roi_pixel_audit import verify


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.samples = [{'table_id': t, 'file': f'table_{t:02d}_sample_{i:03d}.jpg'}
                        for t in range(1, 5) for i in range(120)]

    def test_64_checks_span_4_tables_and_first_last(self):
        chosen = choose_spotcheck(self.samples, [1, 2, 3, 4], 64)
        self.assertEqual(len(chosen), 64)
        for t in range(1, 5):
            subset = [x for x in chosen if x['table_id'] == t]
            self.assertEqual(len(subset), 16)
            self.assertEqual(subset[0]['file'], f'table_{t:02d}_sample_000.jpg')
            self.assertEqual(subset[-1]['file'], f'table_{t:02d}_sample_119.jpg')

    def test_small_budget_each_table(self):
        chosen = choose_spotcheck(self.samples, [1, 2, 3, 4], 4)
        self.assertEqual(len(chosen), 4)
        self.assertEqual({x['table_id'] for x in chosen}, {1, 2, 3, 4})

    def test_more_budget_than_samples_no_duplicates(self):
        small = self.samples[:2] + self.samples[120:122]
        chosen = choose_spotcheck(small, [1, 2], 10)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(len({x['file'] for x in chosen}), 4)

    def test_unequal_table_counts_redistribute_full_budget(self):
        samples = (self.samples[:2] + self.samples[120:220] +
                   self.samples[240:340] + self.samples[360:460])
        chosen = choose_spotcheck(samples, [1, 2, 3, 4], 20)
        self.assertEqual(len(chosen), 20)
        self.assertEqual(len({s['file'] for s in chosen}), 20)
        self.assertEqual({t: sum(s['table_id'] == t for s in chosen)
                          for t in range(1, 5)},
                         {1: 2, 2: 6, 3: 6, 4: 6})

    def test_reject_bad_budget_and_table(self):
        for budget in (0, 3, 65, True, 1.5):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                choose_spotcheck(self.samples, [1, 2, 3, 4], budget)
        with self.assertRaises(ValueError):
            choose_spotcheck([{'table_id': 5, 'file': 'x'}], [1, 2, 3, 4], 4)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and FFprobe are required')
class RealOriginalPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='plo_chain_fixture_')
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'synthetic_vfr.mp4'
        boxes = ','.join(f'drawbox=x={x}:y={y}:w=160:h=120:color={color}:t=fill'
                         for x, y, color in [(0, 0, 'red'), (160, 0, 'green'),
                                             (0, 120, 'blue'), (160, 120, 'yellow')])
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=10:d=2',
                        '-vf', boxes + ",setpts='if(lt(N,10),N,2*N-10)/(10*TB)'",
                        '-fps_mode', 'vfr', '-c:v', 'mpeg4', '-q:v', '4',
                        str(cls.video)], check=True, capture_output=True, timeout=30)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': i, 'x': x, 'y': y, 'width': 160, 'height': 120}
            for i, (x, y) in enumerate([(0, 0), (160, 0), (0, 120), (160, 120)], 1)]}))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_run = tempfile.TemporaryDirectory(prefix='plo_chain_run_')
        self.addCleanup(self.temp_run.cleanup)
        self.out = Path(self.temp_run.name) / 'complete'

    def test_exact_original_ingest_and_both_auditors(self):
        result = run(self.video, self.regions, self.out, pixel_checks=8)
        self.assertEqual(result['tables'], 4)
        self.assertEqual(result['total_crops_pts_hash_audited'], 12)
        self.assertEqual(result['crops_pixel_checked'], 8)
        self.assertTrue(result['vfr_observed'])
        self.assertFalse(result['equity_ev_authorized'])
        self.assertEqual(audit(self.video, self.out / 'ingest')['sample_count'], 12)
        self.assertEqual(len(list((self.out / 'ingest').glob('*.jpg'))), 12)
        for name in ('chain_report.json', 'pts_audit.json', 'pixel_spotcheck.json'):
            self.assertTrue((self.out / name).is_file())
        pixel_report = json.loads((self.out / 'pixel_spotcheck.json').read_text())
        self.assertEqual(pixel_report['samples_checked'], 8)
        self.assertEqual(pixel_report['unique_source_frames_decoded'], 2)

    def test_all_samples_pixel_checked(self):
        result = run(self.video, self.regions, self.out, pixel_checks=64)
        self.assertEqual(result['crops_pixel_checked'], 12)
        self.assertEqual(result['pixel_coverage_fraction'], 1.0)

    def test_cli_and_existing_output_rejected(self):
        self.assertEqual(main([str(self.video), str(self.regions), str(self.out),
                               '--pixel-checks', '4']), 0)
        self.assertTrue(self.out.is_dir())
        with self.assertRaisesRegex(ValueError, 'new safe'):
            run(self.video, self.regions, self.out)

    def test_failed_pixel_audit_leaves_no_output(self):
        with patch('offline_ingest_audited_pipeline.verify', side_effect=ValueError('bad pixels')):
            with self.assertRaisesRegex(ValueError, 'bad pixels'):
                run(self.video, self.regions, self.out, pixel_checks=4)
        self.assertFalse(self.out.exists())

    def test_failed_pts_audit_leaves_no_output(self):
        with patch('offline_ingest_audited_pipeline.audit', side_effect=ValueError('bad PTS')):
            with self.assertRaisesRegex(ValueError, 'bad PTS'):
                run(self.video, self.regions, self.out, pixel_checks=4)
        self.assertFalse(self.out.exists())

    def test_reject_invalid_budget_before_ingest(self):
        for bad in (0, 3, 65, True):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'budget'):
                run(self.video, self.regions, self.out, pixel_checks=bad)
        self.assertFalse(self.out.exists())

    def test_config_mutation_blocks_publish(self):
        from offline_ingest_audited_pipeline import sha256 as real_sha
        def sha(path):
            if Path(path) == self.regions:
                return '0' * 64
            return real_sha(path)
        with patch('offline_ingest_audited_pipeline.sha256', side_effect=sha):
            with self.assertRaisesRegex(ValueError, 'region configuration changed'):
                run(self.video, self.regions, self.out, pixel_checks=4)
        self.assertFalse(self.out.exists())

    def test_65_second_four_table_recording_with_partial_pixel_coverage(self):
        long_video = Path(self.temp_run.name) / 'long_65s.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=2:d=65',
                        '-vf', 'drawbox=x=0:y=0:w=160:h=120:color=red:t=fill,'
                               'drawbox=x=160:y=0:w=160:h=120:color=green:t=fill,'
                               'drawbox=x=0:y=120:w=160:h=120:color=blue:t=fill,'
                               'drawbox=x=160:y=120:w=160:h=120:color=yellow:t=fill',
                        '-c:v', 'mpeg4', '-q:v', '4', str(long_video)],
                       check=True, capture_output=True, timeout=40)
        result = run(long_video, self.regions, self.out, pixel_checks=8)
        self.assertEqual(result['tables'], 4)
        self.assertGreater(result['total_crops_pts_hash_audited'], 8)
        self.assertEqual(result['crops_pixel_checked'], 8)
        self.assertLess(result['pixel_coverage_fraction'], 1)
        self.assertFalse(result['equity_ev_authorized'])

    def test_nonzero_source_pts_preserved(self):
        offset_video = Path(self.temp_run.name) / 'offset.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=5:duration=2',
                        '-vf', 'setpts=PTS+5/TB', '-fps_mode', 'passthrough',
                        '-c:v', 'mpeg4', '-q:v', '5', str(offset_video)],
                       check=True, capture_output=True, timeout=30)
        result = run(offset_video, self.regions, self.out, pixel_checks=4)
        manifest = json.loads((self.out / 'ingest' / 'manifest.json').read_text())
        self.assertTrue(all(s['actual_frame_timestamp_seconds'] >= 5
                            for s in manifest['samples']))
        self.assertEqual(result['total_crops_pts_hash_audited'], 12)

    def test_source_untouched(self):
        from offline_ingest_pts_audit import digest
        original = digest(self.video)
        run(self.video, self.regions, self.out, pixel_checks=4)
        self.assertEqual(digest(self.video), original)


if __name__ == '__main__':
    unittest.main()
