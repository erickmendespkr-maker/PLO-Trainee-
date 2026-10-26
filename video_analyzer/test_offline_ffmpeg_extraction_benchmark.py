"""Synthetic-only benchmark and B-frame seek regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from offline_ffmpeg_extraction_benchmark import benchmark, main
from offline_ffmpeg_seek_frame_provenance import seek_video_frames
from offline_ffmpeg_extraction_benchmark import _synthetic


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class ExtractionBenchmarkTests(unittest.TestCase):
    def test_bframe_seek_near_terminal_gop_uses_verified_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "source.mp4"
            _synthetic(video, 6, 10, 10)
            diagnostics = {}
            frames = seek_video_frames(video, [55], root, 6.0, diagnostics=diagnostics)
            self.assertEqual(diagnostics["full_decode_fallbacks"], 1)
            self.assertAlmostEqual(frames[55][1], 5.5)
            self.assertTrue(frames[55][0].is_file())

    def test_two_gop_benchmark_includes_probe_and_exact_comparison(self):
        data = benchmark(seconds=4, fps=10, gops=(10, 20), indices=(1, 20, 35))
        self.assertEqual(len(data["runs"]), 2)
        self.assertFalse(data["real_session_performance_verified"])
        self.assertFalse(data["equity_ev_authorized"])
        for run in data["runs"]:
            self.assertTrue(run["exact_png_and_pts_match"])
            self.assertGreaterEqual(run["full_decode_fallbacks"], 0)
            self.assertEqual([f["index"] for f in run["frames"]], [1, 20, 35])
            self.assertGreater(run["full_decode_seconds"], 0)
            self.assertGreater(run["indexed_seek_including_probe_seconds"], 0)

    def test_cli_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            self.assertEqual(main([str(path), "--seconds", "3", "--fps", "10",
                                   "--gops", "10", "--indices", "2,20"]), 0)
            self.assertEqual(json.loads(path.read_text())["fixture"]["indices"], [2, 20])
            with self.assertRaisesRegex(ValueError, "new JSON"):
                main([str(path), "--seconds", "3", "--fps", "10",
                      "--gops", "10", "--indices", "2,20"])

    def test_reject_invalid_configuration(self):
        for kwargs in ({"seconds": 1}, {"seconds": 91}, {"fps": 0},
                       {"gops": (0,)}, {"gops": (10, 10)},
                       {"seconds": 3, "fps": 10, "indices": (30,)},
                       {"indices": (3, 1)}, {"indices": (1, 1)},
                       {"gops": (10, 20, 30, 40)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                benchmark(**kwargs)


if __name__ == "__main__":
    unittest.main()
