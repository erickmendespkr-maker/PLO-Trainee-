"""Bounded synthetic FFmpeg benchmark matrix regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from offline_ffmpeg_benchmark_matrix import matrix, main, spaced_indices


class MatrixValidationTests(unittest.TestCase):
    def test_spaced_indices(self):
        self.assertEqual(spaced_indices(6, 10, 3), (14, 29, 44))
        self.assertEqual(len(spaced_indices(6, 10, 12)), 12)

    def test_invalid_configurations(self):
        cases = [
            {'durations': (1,)}, {'durations': (91,)},
            {'durations': (6, 6)}, {'durations': (6, 12, 30, 60)},
            {'counts': (0,)}, {'counts': (13,)}, {'counts': (1, 1)},
            {'gops': (1,)}, {'gops': (10, 10)}, {'gops': (10, 60, 100, 120)},
            {'fps': 0}, {'fps': 31}, {'repeats': 1}, {'repeats': 5},
            {'durations': (6, 12, 30), 'counts': (1, 5, 9),
             'gops': (10, 60, 90), 'repeats': 2},
        ]
        for kw in cases:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                matrix(**kw)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class MatrixExecutionTests(unittest.TestCase):
    def test_repeated_synthetic_matrix(self):
        result = matrix(durations=(3,), fps=10, counts=(1, 3), gops=(10,), repeats=2)
        self.assertEqual(result['runs_count'], 4)
        self.assertEqual(len(result['configurations']), 2)
        self.assertFalse(result['automatic_strategy_selection_authorized'])
        self.assertFalse(result['real_session_performance_verified'])
        for item in result['configurations']:
            self.assertTrue(item['exact_png_and_pts_match_in_all_runs'])
            self.assertEqual(len(item['full_decode_seconds_runs']), 2)
            self.assertGreater(item['full_decode_median_seconds'], 0)
            self.assertGreater(item['indexed_seek_median_seconds'], 0)

    def test_cli_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'matrix.json'
            args = [str(output), '--durations', '3', '--fps', '10',
                    '--counts', '2', '--gops', '10', '--repeats', '2']
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(output.read_text())['runs_count'], 2)
            with self.assertRaisesRegex(ValueError, 'new JSON'):
                main(args)


if __name__ == '__main__':
    unittest.main()
