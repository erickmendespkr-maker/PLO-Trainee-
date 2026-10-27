"""Synthetic, offline regression tests for four-table sample extraction."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_four_table_sample_review as m


def make_video(path, *, width=320, height=240, fps=5, duration=3):
    # Four distinct colored quadrants; no poker graphics or real player data.
    filters = (f"drawbox=x=0:y=0:w={width//2}:h={height//2}:color=red:t=fill,"
               f"drawbox=x={width//2}:y=0:w={width-width//2}:h={height//2}:color=green:t=fill,"
               f"drawbox=x=0:y={height//2}:w={width//2}:h={height-height//2}:color=blue:t=fill,"
               f"drawbox=x={width//2}:y={height//2}:w={width-width//2}:h={height-height//2}:color=yellow:t=fill")
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration}",
                    "-vf", filters, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-y", str(path)], check=True, capture_output=True, timeout=30)


def average_rgb(path):
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                           "-i", str(path), "-vf", "scale=1:1", "-frames:v", "1",
                           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                          capture_output=True, check=True, timeout=15)
    return tuple(proc.stdout[:3])


class FourTableReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("FFmpeg and FFprobe required for integration tests")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "session.mp4"
        make_video(self.video)
        self.layout = self.root / "layout.json"
        self.grid = {"schema_version": 1, "layout": "grid", "rows": 2, "columns": 2}
        self.write_layout(self.grid)
        self.out = self.root / "review"

    def write_layout(self, obj):
        self.layout.write_text(json.dumps(obj), encoding="utf-8")

    def build(self, times=None):
        return m.build(self.video, self.layout, self.out, [0.2, 1.2, 2.2] if times is None else times)

    def test_four_regions_three_timestamps_and_integrity(self):
        report = self.build()
        self.assertEqual(len(report["regions"]), 4)
        self.assertEqual(len(report["samples"]), 3)
        self.assertEqual(len(list((self.out / "tables").glob("*.png"))), 12)
        self.assertEqual(len(list((self.out / "frames").glob("*.png"))), 3)
        self.assertEqual(m.verify_bundle(self.out, self.video), report)

    def test_crop_quadrants_are_distinct_and_correct(self):
        self.build([0.2])
        pixels = [average_rgb(self.out / f"tables/table_{i:02d}_sample_00.png")
                  for i in range(1, 5)]
        # Approximate channel dominance, allowing codec conversion and scaling.
        self.assertGreater(pixels[0][0], pixels[0][1] + 70)  # red
        self.assertGreater(pixels[1][1], pixels[1][0] + 40)  # green
        self.assertGreater(pixels[2][2], pixels[2][0] + 70)  # blue
        self.assertGreater(pixels[3][0], pixels[3][2] + 70)  # yellow
        self.assertGreater(pixels[3][1], pixels[3][2] + 70)

    def test_source_pts_is_not_relative_seek_pts(self):
        report = self.build([1.1])
        row = report["samples"][0]
        self.assertAlmostEqual(row["decoded_source_pts_seconds"], 1.2, places=2)
        self.assertAlmostEqual(row["seek_delta_seconds"], 0.1, places=2)

    def test_html_is_offline_and_has_review_warning(self):
        self.build([0.2])
        page = (self.out / "review.html").read_text(encoding="utf-8")
        self.assertIn("Revisão humana obrigatória", page)
        self.assertIn("tables/table_01_sample_00.png", page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_fail_closed_flags(self):
        report = self.build([0.2])
        for key in ("regions_human_confirmed", "cards_actions_verified",
                    "hand_boundaries_verified", "ready_for_equity_or_ev",
                    "automatic_clip_selection_authorized"):
            self.assertIs(report[key], False)

    def test_tampered_png_rejected(self):
        self.build([0.2])
        p = self.out / "tables/table_01_sample_00.png"
        p.write_bytes(p.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "hash"):
            m.verify_bundle(self.out)

    def test_tampered_manifest_flags_rejected(self):
        self.build([0.2])
        p = self.out / "region_samples.json"
        doc = json.loads(p.read_text())
        doc["ready_for_equity_or_ev"] = True
        p.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "Unsafe bundle"):
            m.verify_bundle(self.out)

    def test_wrong_source_sha_rejected(self):
        self.build([0.2])
        other = self.root / "other.mp4"
        other.write_bytes(b"not the recording")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            m.verify_bundle(self.out, other)

    def test_existing_output_never_overwritten(self):
        self.out.mkdir()
        (self.out / "sentinel").write_text("keep")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.build([0.2])
        self.assertEqual((self.out / "sentinel").read_text(), "keep")

    def test_reject_symlink_recording(self):
        link = self.root / "link.mp4"
        link.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, "Unsafe recording"):
            m.build(link, self.layout, self.out, [0.2])

    def test_reject_symlink_layout(self):
        actual = self.root / "real.json"
        self.layout.rename(actual)
        self.layout.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "Invalid JSON input"):
            self.build([0.2])

    def test_reject_duplicate_json_keys(self):
        self.layout.write_text('{"schema_version":1,"layout":"grid","rows":2,"rows":2,"columns":2}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            self.build([0.2])

    def test_reject_nan_layout(self):
        self.layout.write_text('{"schema_version":1,"layout":"grid","rows":NaN,"columns":2}')
        with self.assertRaises(ValueError):
            self.build([0.2])

    def test_reject_invalid_grid_count(self):
        self.write_layout({"schema_version": 1, "layout": "grid", "rows": 2, "columns": 3})
        with self.assertRaisesRegex(ValueError, "one to four"):
            self.build([0.2])

    def test_reject_manual_overlap(self):
        self.write_layout({"schema_version": 1, "layout": "manual", "regions": [
            {"table_id": 1, "x": 0, "y": 0, "width": 160, "height": 120},
            {"table_id": 2, "x": 80, "y": 0, "width": 160, "height": 120}]})
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.build([0.2])

    def test_manual_two_regions_supported(self):
        self.write_layout({"schema_version": 1, "layout": "manual", "regions": [
            {"table_id": 1, "x": 0, "y": 0, "width": 160, "height": 120},
            {"table_id": 4, "x": 160, "y": 120, "width": 160, "height": 120}]})
        report = self.build([0.2])
        self.assertEqual([x["table_id"] for x in report["regions"]], [1, 4])
        self.assertEqual(len(report["samples"][0]["table_crops"]), 2)
        m.verify_bundle(self.out, self.video)

    def test_reject_boolean_region_coordinate(self):
        self.write_layout({"schema_version": 1, "layout": "manual", "regions": [
            {"table_id": 1, "x": True, "y": 0, "width": 160, "height": 120}]})
        with self.assertRaisesRegex(ValueError, "Invalid manual region"):
            self.build([0.2])

    def test_reject_unsorted_duplicate_or_outside_times(self):
        for values in ([0.5, 0.5], [1.5, 0.5], [-1], [4], [float("nan")], [True], []):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.build(values)
        self.assertFalse(self.out.exists())

    def test_reject_over_budget_samples(self):
        with self.assertRaisesRegex(ValueError, "one to eight"):
            self.build([i / 10 for i in range(9)])

    def test_failure_does_not_publish_partial_directory(self):
        with mock.patch.object(m, "MAX_TOTAL_IMAGE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "budget"):
                self.build([0.2])
        self.assertFalse(self.out.exists())

    def test_verify_rejects_symlink_crop(self):
        self.build([0.2])
        p = self.out / "tables/table_01_sample_00.png"
        actual = self.root / "original.png"
        p.rename(actual)
        p.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "Invalid PNG"):
            m.verify_bundle(self.out)

    def test_verify_rejects_misleading_pts(self):
        self.build([0.2])
        p = self.out / "region_samples.json"
        report = json.loads(p.read_text())
        report["samples"][0]["decoded_source_pts_seconds"] = 0.0
        p.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "timestamp provenance"):
            m.verify_bundle(self.out)

    def test_webm_vp9_source_pts(self):
        webm = self.root / "session.webm"
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-i", str(self.video), "-c:v", "libvpx-vp9", "-b:v", "250k",
                        "-an", "-y", str(webm)], check=True, capture_output=True, timeout=45)
        report = m.build(webm, self.layout, self.out, [0.2, 1.2])
        self.assertAlmostEqual(report["samples"][1]["decoded_source_pts_seconds"], 1.2, places=2)
        m.verify_bundle(self.out, webm)

    def test_vfr_gap_is_reported_not_concealed(self):
        vfr = self.root / "vfr.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5:duration=3",
                        "-vf", "setpts=PTS+if(gte(N\\,5)\\,0.4/TB\\,0)",
                        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-y", str(vfr)], check=True, capture_output=True, timeout=30)
        report = m.build(vfr, self.layout, self.out, [1.0])
        self.assertAlmostEqual(report["samples"][0]["decoded_source_pts_seconds"], 1.4, places=2)
        self.assertAlmostEqual(report["samples"][0]["seek_delta_seconds"], 0.4, places=2)
        m.verify_bundle(self.out, vfr)

    def test_verify_rejects_unordered_manifest_times(self):
        self.build([0.2, 1.2])
        path = self.out / "region_samples.json"
        doc = json.loads(path.read_text())
        doc["samples"][1]["requested_seek_seconds"] = 0.1
        doc["samples"][1]["seek_delta_seconds"] = round(
            doc["samples"][1]["decoded_source_pts_seconds"] - 0.1, 6)
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "timestamp provenance"):
            m.verify_bundle(self.out)

    def test_cli_build_and_verify(self):
        code = m.main(["build", str(self.video), str(self.layout), str(self.out),
                       "--times", "0.2,1.2"])
        self.assertEqual(code, 0)
        self.assertEqual(m.main(["verify", str(self.out), "--recording", str(self.video)]), 0)


if __name__ == "__main__":
    unittest.main()