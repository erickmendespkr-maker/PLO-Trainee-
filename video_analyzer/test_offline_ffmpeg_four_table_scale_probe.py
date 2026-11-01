"""Synthetic four-table FFmpeg extraction and resource reporting regression tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_ffmpeg_four_table_scale_probe as b


class FourTableFFmpegScaleTests(unittest.TestCase):
    def test_sample_schedule_bounds(self):
        self.assertEqual(b.sample_times(8, 2), [0, 2, 4, 6])
        self.assertEqual(b.sample_times(2400, 600), [0, 600, 1200, 1800, 2398])

    def test_invalid_input_rejected(self):
        for seconds, interval in [(7, 2), (3601, 600), (True, 10), (60, True),
                                  (60, 0), (60, 1201), (3600, 2)]:
            with self.subTest(seconds=seconds, interval=interval):
                with self.assertRaises(ValueError):
                    b.sample_times(seconds, interval)

    def test_expected_color_predicates(self):
        for color, rgb in [('red', (255, 0, 0)), ('green', (0, 128, 0)),
                           ('blue', (0, 0, 255)), ('yellow', (255, 255, 0))]:
            self.assertTrue(b.is_expected_color(rgb, color))
            for other in ('red', 'green', 'blue', 'yellow'):
                if other != color:
                    self.assertFalse(b.is_expected_color(rgb, other))

    def test_four_table_end_to_end_ffmpeg(self):
        result = b.benchmark(seconds=8, interval=2)
        self.assertEqual(result['table_count'], 4)
        self.assertEqual(result['total_crops'], 16)
        self.assertEqual(result['samples_per_table'], 4)
        self.assertTrue(result['all_crops_verified'])
        self.assertEqual({x['table_id'] for x in result['samples']}, {1, 2, 3, 4})
        self.assertTrue(all(x['roi_color_test'] == 'passed' for x in result['samples']))
        self.assertFalse(result['ocr_verified'])
        self.assertFalse(result['real_video_verified'])
        self.assertGreater(result['fixture']['size_bytes'], 0)
        self.assertGreater(result['crop_bytes_total'], 0)

    def test_output_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'report.json'
            b.write_new({'status': b.STATUS}, target)
            self.assertEqual(json.loads(target.read_text())['status'], b.STATUS)
            with self.assertRaises(ValueError):
                b.write_new({}, target)

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / 'existing.json'
            other.write_text('original')
            target = Path(d) / 'report.json'
            target.symlink_to(other)
            with self.assertRaises(ValueError):
                b.write_new({}, target)
            self.assertEqual(other.read_text(), 'original')

    def test_bad_extension_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                b.write_new({}, Path(d) / 'report.txt')

    def test_command_failure_closed(self):
        with self.assertRaises(ValueError):
            b.command(['not-a-real-executable-plo-test'], timeout=1)


if __name__ == '__main__':
    unittest.main()
