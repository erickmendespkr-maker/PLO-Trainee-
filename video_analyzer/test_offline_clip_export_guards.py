"""Negative-path integration tests for the offline FFmpeg exporter.

Run from video_analyzer: python -m unittest -v test_offline_clip_export_guards
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_clip_export import export_clip, sha256_file


class ExportGuardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "input.mp4"
        # No actual media required for checks that must fail before probing.
        self.source.write_bytes(b"synthetic non-media input")
        self.out = self.root / "out"
        self.plan = {
            "source_sha256": sha256_file(self.source),
            "table_id": 1, "hand_id": "synthetic-1",
            "start_seconds": 0, "end_seconds": 1,
            "duration_seconds": 1, "output_name": "clip.mp4",
            "review_status": "insufficient_data",
            "strategic_verdict_allowed": False,
        }

    def test_wrong_hash_rejected_before_ffprobe_and_output_creation(self):
        bad = dict(self.plan, source_sha256="0" * 64)
        with patch("offline_clip_export.probe_duration") as probe:
            with self.assertRaises(ValueError):
                export_clip(self.source, self.out, bad)
            probe.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_invalid_table_rejected_before_output_creation(self):
        bad = dict(self.plan, table_id=True)
        with patch("offline_clip_export.probe_duration") as probe:
            with self.assertRaises(ValueError):
                export_clip(self.source, self.out, bad)
            probe.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_source_symlink_rejected_before_probe(self):
        link = self.root / "linked.mp4"
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with patch("offline_clip_export.probe_duration") as probe:
            with self.assertRaises(ValueError):
                export_clip(link, self.out, self.plan)
            probe.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_interval_beyond_source_rejected_before_ffmpeg(self):
        with patch("offline_clip_export.probe_duration", return_value=0.5):
            with patch("offline_clip_export.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    export_clip(self.source, self.out, self.plan)
                run.assert_not_called()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_sidecar_never_overwritten(self):
        self.out.mkdir()
        sidecar = self.out / "clip.mp4.json"
        sidecar.write_text("competitor", encoding="utf-8")
        with patch("offline_clip_export.probe_duration", return_value=2):
            with patch("offline_clip_export.subprocess.run") as run:
                with self.assertRaises(FileExistsError):
                    export_clip(self.source, self.out, self.plan)
                run.assert_not_called()
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "competitor")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["clip.mp4.json"])


if __name__ == "__main__":
    unittest.main()
