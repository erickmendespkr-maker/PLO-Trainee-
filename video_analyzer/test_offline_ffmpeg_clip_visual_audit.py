"""Synthetic regression tests for terminal decoded-frame thumbnail diagnostics."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ffmpeg_clip_visual_audit import compare, main


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class VisualAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "source.mp4"
        cls.clip = cls.root / "clip.mp4"
        cls.short = cls.root / "short.mp4"
        cls.different = cls.root / "different.mp4"
        cls.remux = cls.root / "remux.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-q:v", "2", str(cls.source)], check=True)
        for path, duration in ((cls.clip, 1), (cls.short, .5)):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", "1", "-i", str(cls.source), "-t", str(duration),
                            "-an", "-c:v", "mpeg4", "-q:v", "2", str(path)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=red:s=160x120:r=10:d=1", "-an", "-c:v",
                        "mpeg4", "-q:v", "2", str(cls.different)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i",
                        str(cls.source), "-c", "copy", "-movflags", "+faststart",
                        str(cls.remux)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reencoded_clip_end_similar(self):
        report = compare(self.source, self.clip, 1)
        self.assertEqual(report["timing_classification"], "within_one_frame_tolerance")
        self.assertIn(report["thumbnail_classification"],
                      ("near_identical_thumbnail", "similar_thumbnail"))
        self.assertFalse(report["visual_provenance_verified"])
        self.assertFalse(report["equity_ev_authorized"])

    def test_remux_identical_decoded_end(self):
        report = compare(self.source, self.remux, 0)
        self.assertEqual(report["thumbnail_classification"], "near_identical_thumbnail")
        self.assertEqual(report["mean_absolute_gray_error_0_to_255"], 0)

    def test_different_last_frame_detected(self):
        report = compare(self.source, self.different, 1)
        self.assertEqual(report["thumbnail_classification"], "different_thumbnail")
        self.assertGreater(report["mean_absolute_gray_error_0_to_255"], 8)

    def test_short_clip_timing_shortfall(self):
        report = compare(self.source, self.short, 1)
        self.assertEqual(report["timing_classification"], "shorter_than_expected")
        self.assertFalse(report["last_frame_duplicated_or_missing_verified"])

    def test_reject_same_file(self):
        with self.assertRaisesRegex(ValueError, "identical"):
            compare(self.source, self.source, 0)

    def test_reject_missing_source(self):
        with self.assertRaises(ValueError):
            compare(self.root / "absent.mp4", self.clip, 1)

    def test_reject_invalid_start(self):
        with self.assertRaisesRegex(ValueError, "Invalid requested start"):
            compare(self.source, self.clip, float("nan"))

    def test_cli_writes_without_overwrite(self):
        report = self.root / "visual_report.json"
        if report.exists():
            report.unlink()
        self.assertEqual(main([str(self.source), str(self.clip), "1", str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())["schema_version"], 1)
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            main([str(self.source), str(self.clip), "1", str(report)])

    def test_changed_video_after_decode_rejected(self):
        from offline_ffmpeg_clip_visual_audit import source_hash as real_hash
        with patch("offline_ffmpeg_clip_visual_audit.source_hash", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "Video changed"):
                compare(self.source, self.clip, 1)

    def test_symlink_clip_rejected(self):
        alias = self.root / "alias.mp4"
        alias.symlink_to(self.clip)
        with self.assertRaisesRegex(ValueError, "Unsafe recording"):
            compare(self.source, alias, 1)


if __name__ == "__main__":
    unittest.main()
