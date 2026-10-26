"""Synthetic FFmpeg clip end audit regression tests."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ffmpeg_clip_end_audit import audit, packet_span, main


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class ClipAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "source.mp4"
        cls.full = cls.root / "full.mp4"
        cls.short = cls.root / "short.mp4"
        cls.vfr = cls.root / "vfr.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-q:v", "2", str(cls.source)], check=True)
        for output, duration in ((cls.full, 1), (cls.short, .5)):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", "1", "-i", str(cls.source), "-t", str(duration),
                            "-an", "-c:v", "mpeg4", "-q:v", "2", str(output)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=1",
                        "-vf", "setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
                        "-fps_mode", "vfr", "-c:v", "mpeg4", "-q:v", "2", str(cls.vfr)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_packet_span(self):
        data = packet_span(self.source)
        self.assertEqual(data["video_packet_count"], 20)
        self.assertAlmostEqual(data["presentation_span_seconds"], 2)
        self.assertAlmostEqual(data["last_presentation_packet_duration_seconds"], .1)

    def test_full_end_within_one_frame(self):
        result = audit(self.source, self.full, 1)
        self.assertEqual(result["classification"], "within_one_frame_tolerance")
        self.assertFalse(result["source_clip_visual_correspondence_verified"])

    def test_short_end_flagged(self):
        result = audit(self.source, self.short, 1)
        self.assertEqual(result["classification"], "shorter_than_expected")
        self.assertLess(result["difference_seconds"], -.4)

    def test_no_fabricated_video_end(self):
        result = audit(self.source, self.full, 1)
        self.assertFalse(result["last_frame_duplicated_or_missing_verified"])

    def test_vfr_span_from_pts_not_nominal_fps(self):
        result = packet_span(self.vfr)
        self.assertGreater(result["presentation_span_seconds"], 1.2)
        self.assertEqual(result["video_packet_count"], 10)

    def test_invalid_negative_start(self):
        with self.assertRaisesRegex(ValueError, "Invalid requested start"):
            audit(self.source, self.full, -1)

    def test_invalid_boolean_start(self):
        with self.assertRaisesRegex(ValueError, "Invalid requested start"):
            audit(self.source, self.full, True)

    def test_start_outside_source(self):
        with self.assertRaisesRegex(ValueError, "beyond source"):
            audit(self.source, self.full, 2)

    def test_same_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "identical"):
            audit(self.source, self.source, 0)

    def test_missing_video(self):
        with self.assertRaises(ValueError):
            packet_span(self.root / "missing.mp4")

    def test_symlink_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            symlink = Path(tmp) / "link.mp4"
            symlink.symlink_to(self.source)
            with self.assertRaisesRegex(ValueError, "Unsafe recording"):
                packet_span(symlink)

    def test_no_overwrite_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            self.assertEqual(main([str(self.source), str(self.full), "1", str(report)]), 0)
            self.assertEqual(json.loads(report.read_text())["classification"], "within_one_frame_tolerance")
            with self.assertRaisesRegex(ValueError, "Unsafe output"):
                main([str(self.source), str(self.full), "1", str(report)])

    def test_missing_duration_rejected(self):
        fake = type("RunResult", (), {"stdout": b'{"packets":[{"pts_time":"0"}]}'})()
        with patch("offline_ffmpeg_clip_end_audit.run", return_value=fake):
            with self.assertRaisesRegex(ValueError, "Packet PTS/duration missing"):
                packet_span(self.source)

    def test_empty_packets_rejected(self):
        fake = type("RunResult", (), {"stdout": b'{"packets":[]}'})()
        with patch("offline_ffmpeg_clip_end_audit.run", return_value=fake):
            with self.assertRaisesRegex(ValueError, "Missing/too many"):
                packet_span(self.source)


if __name__ == "__main__":
    unittest.main()