"""Regression tests for partial crop cleanup, using synthetic files only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
try:
    from . import offline_table_crop as crop
except ImportError:
    import offline_table_crop as crop


class CropCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"synthetic placeholder")
        self.out = self.root / "out"
        self.regions = [
            {"table_id": 1, "x": 0, "y": 0, "width": 100, "height": 100},
            {"table_id": 2, "x": 100, "y": 0, "width": 100, "height": 100},
        ]

    @patch.object(crop, "validate_regions", side_effect=lambda regions, w, h: regions)
    @patch.object(crop, "probe_dimensions", return_value=(200, 100))
    def test_second_ffmpeg_failure_removes_all_crops(self, _probe, _validate):
        calls = []
        def render(command, **kwargs):
            destination = Path(command[-1])
            destination.write_bytes(b"partial video")
            calls.append(destination)
            if len(calls) == 2:
                raise RuntimeError("synthetic FFmpeg failure")
        with patch.object(crop.subprocess, "run", side_effect=render):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                crop.export_table_crops(self.source, self.out, self.regions,
                                        start_seconds=0, duration_seconds=2)
        self.assertEqual(list(self.out.iterdir()), [])

    @patch.object(crop, "validate_regions", side_effect=lambda regions, w, h: regions)
    @patch.object(crop, "probe_dimensions", return_value=(200, 100))
    def test_success_preserves_crops_and_manifest(self, _probe, _validate):
        def render(command, **kwargs):
            Path(command[-1]).write_bytes(b"synthetic")
        with patch.object(crop.subprocess, "run", side_effect=render):
            result = crop.export_table_crops(self.source, self.out, self.regions,
                                             start_seconds=0, duration_seconds=2)
        self.assertEqual(len(result["tables"]), 2)
        self.assertEqual(len(list(self.out.iterdir())), 3)
        self.assertFalse(result["poker_analysis_verified"])


if __name__ == "__main__":
    unittest.main()
