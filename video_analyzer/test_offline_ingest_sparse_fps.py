"""Synthetic regression for sparse frame rates, decoded PTS and periodic planning."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_video_ingest_probe import (build, nominal_fps, sample_times)


class SparseFpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.config = self.base / 'regions.json'
        self.config.write_text(json.dumps({'tables': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180},
            {'table_id': 2, 'x': 320, 'y': 0, 'width': 320, 'height': 180}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def video(self, fps=1, seconds=3):
        path = self.base / f'synthetic_{fps}_{seconds}.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', f'testsrc2=size=640x180:rate={fps}',
                        '-t', str(seconds), '-c:v', 'mpeg4', '-y', str(path)],
                       check=True, capture_output=True)
        return path

    def test_one_fps_last_frame_and_pts(self):
        report = build(self.video(1, 3), self.config, self.base / 'one_fps')
        self.assertEqual(len(report['samples']), 6)
        self.assertEqual({x['timestamp_seconds'] for x in report['samples']}, {0, 1, 2})
        self.assertEqual({x['actual_frame_timestamp_seconds'] for x in report['samples']}, {0, 1, 2})
        self.assertTrue(all(x['seek_attempts'] >= 1 for x in report['samples']))

    def test_two_second_one_fps_deduplicates(self):
        report = build(self.video(1, 2), self.config, self.base / 'two_fps')
        self.assertEqual(len(report['samples']), 4)
        self.assertEqual({x['actual_frame_timestamp_seconds'] for x in report['samples']}, {0, 1})

    def test_nominal_fps_is_not_truth(self):
        self.assertEqual(nominal_fps('30000/1001'), 30000 / 1001)
        self.assertIsNone(nominal_fps('0/0'))
        self.assertIsNone(nominal_fps('unknown'))
        self.assertIsNone(nominal_fps('1000/1'))
        self.assertEqual(sample_times(2), [0.25, 1.0, 1.75])

    def test_periodic_sampling_is_bounded(self):
        times = sample_times(3600, '1/1', 30)
        self.assertTrue(120 <= len(times) <= 125)
        self.assertEqual(times[0], 0)
        self.assertEqual(times[-1], 3599)
        self.assertIn(1800, times)
        self.assertEqual(len(times), len(set(times)))

    def test_invalid_interval_rejected_without_output(self):
        video = self.video()
        for interval in (0, 4.9, 121, float('nan'), float('inf'), '30', True):
            out = self.base / 'bad'
            with self.assertRaises(ValueError):
                build(video, self.config, out, interval_seconds=interval)
            self.assertFalse(out.exists())

    def test_two_fps_real_pts_and_integrity(self):
        report = build(self.video(2, 3), self.config, self.base / 'twofps')
        self.assertEqual(len(report['samples']), 6)
        self.assertTrue(all('actual_frame_timestamp_seconds' in x for x in report['samples']))
        self.assertTrue(all((self.base / 'twofps' / x['file']).is_file() for x in report['samples']))
        self.assertEqual(json.loads((self.base / 'twofps' / 'manifest.json').read_text()), report)


if __name__ == '__main__':
    unittest.main()
