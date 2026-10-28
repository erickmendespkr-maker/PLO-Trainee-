"""Synthetic, local-only FFmpeg regression tests for offline ingest preflight."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_video_ingest_probe import (build, no_duplicates, probe, sha256,
                                        regions_from_json, sample_times)


class OfflineIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.base = Path(cls.root.name)
        cls.video = cls.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=640x360:rate=5', '-t', '2',
                        '-c:v', 'mpeg4', '-y', str(cls.video)], check=True)
        cls.config = cls.base / 'regions.json'
        cls.regions = [dict(table_id=i + 1, x=(i % 2) * 320,
                            y=(i // 2) * 180, width=320, height=180)
                       for i in range(4)]
        cls.config.write_text(json.dumps({'tables': cls.regions}), 'utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def test_real_ffmpeg_four_tables(self):
        out = self.base / 'four_tables'
        report = build(self.video, self.config, out)
        self.assertEqual(len(report['samples']), 12)
        self.assertEqual(len(report['regions']), 4)
        self.assertEqual(report['media']['width'], 640)
        self.assertEqual(report['media']['height'], 360)
        self.assertEqual(report['analysis_status'], 'offline_sampled_video_preflight_no_ocr')
        for item in report['samples']:
            frame = out / item['file']
            self.assertEqual(hashlib.sha256(frame.read_bytes()).hexdigest(), item['sha256'])
            data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                '-of', 'json', str(frame)]))
            self.assertEqual((data['streams'][0]['width'], data['streams'][0]['height']), (320, 180))
        self.assertEqual(json.loads((out / 'manifest.json').read_text()), report)

    def test_refuse_existing_output(self):
        existing = self.base / 'already_exists'
        existing.mkdir(exist_ok=True)
        with self.assertRaises(ValueError):
            build(self.video, self.config, existing)

    def test_duration_and_probe(self):
        self.assertEqual(probe(self.video)['duration_seconds'], 2)
        self.assertEqual(sample_times(2), [0.25, 1, 1.75])
        self.assertEqual(sample_times(1), [0.5])

    def test_reject_duplicate_json_key(self):
        with self.assertRaises(ValueError):
            no_duplicates([('tables', []), ('tables', [])])

    def test_reject_overflow(self):
        invalid = self.base / 'invalid_regions.json'
        invalid.write_text(json.dumps({'tables': [dict(self.regions[0], x=500)]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_boolean_as_integer(self):
        invalid = self.base / 'bool_regions.json'
        invalid.write_text(json.dumps({'tables': [dict(self.regions[0], x=True)]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_duplicate_table_id(self):
        invalid = self.base / 'dupe_regions.json'
        invalid.write_text(json.dumps({'tables': [self.regions[0], self.regions[0]]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_more_than_four(self):
        invalid = self.base / 'five_regions.json'
        invalid.write_text(json.dumps({'tables': self.regions + [dict(self.regions[0], table_id=5)]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_overlapping_regions(self):
        invalid = self.base / 'overlap_regions.json'
        invalid.write_text(json.dumps({'tables': [self.regions[0], dict(self.regions[1], x=200)]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_odd_crop(self):
        invalid = self.base / 'odd_regions.json'
        invalid.write_text(json.dumps({'tables': [dict(self.regions[0], x=1)]}), 'utf-8')
        with self.assertRaises(ValueError):
            regions_from_json(invalid, 640, 360)

    def test_reject_symlink_recording(self):
        symlink = self.base / 'symlink.mp4'
        symlink.symlink_to(self.video)
        with self.assertRaises(ValueError):
            build(symlink, self.config, self.base / 'symlink_out')

    def test_reject_modified_input(self):
        counter = [0]
        def changed_on_second_video_hash(path):
            if Path(path) == self.video:
                counter[0] += 1
                if counter[0] == 2:
                    return 'changed'
            return sha256(path)
        with patch('offline_video_ingest_probe.sha256', side_effect=changed_on_second_video_hash):
            with self.assertRaises(ValueError):
                build(self.video, self.config, self.base / 'tampered_out')
        self.assertFalse((self.base / 'tampered_out').exists())


if __name__ == '__main__':
    unittest.main()
