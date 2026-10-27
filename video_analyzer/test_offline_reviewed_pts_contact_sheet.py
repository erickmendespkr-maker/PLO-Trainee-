"""Synthetic, offline-only frame-reference tests. No real poker recognition."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_reviewed_pts_contact_sheet import export, main, _samples, _indices
from offline_reviewed_source_pts_audit import _scan_pts
import test_offline_reviewed_decision_timeline as fixture_module


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg/FFprobe required")
class ContactSheetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.DecisionTimelineTests("test_success_and_blocked_sorted")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.video = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=3",
                        "-c:v", "mpeg4", str(self.video)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.fixture.source = hashlib.sha256(self.video.read_bytes()).hexdigest()

    def make(self, *args, **kwargs):
        return self.fixture.make(*args, **kwargs)

    def export(self, name="references", **kwargs):
        return export(self.video, self.fixture.dirs, self.root / name, **kwargs)

    def test_flagged_points_produce_exact_decoded_frames(self):
        self.make(moment=1.55)
        result = self.export(tolerance_seconds=0.02)
        self.assertEqual(len(result["review_points"]), 3)
        self.assertGreaterEqual(len(result["reference_images"]), 3)
        self.assertEqual(result["timestamps_outside_tolerance"], 3)
        self.assertFalse(result["approved_for_export"])
        self.assertFalse(result["video_content_verified"])
        self.assertEqual(json.loads((self.root / "references" / "review_template.json").read_text()), result)
        for meta in result["reference_images"].values():
            frame = self.root / "references" / meta["file"]
            self.assertTrue(frame.is_file())
            self.assertEqual(hashlib.sha256(frame.read_bytes()).hexdigest(), meta["sha256"])

    def test_no_flags_creates_safe_empty_report(self):
        self.make(moment=1.5)
        result = self.export()
        self.assertEqual(result["review_points"], [])
        self.assertEqual(result["reference_images"], {})
        self.assertIn("Nenhum timestamp sinalizado", (self.root / "references" / "contact_sheet.html").read_text())

    def test_include_decision_samples(self):
        self.make(moment=1.5)
        result = self.export(include_decisions=True)
        self.assertEqual([p["kind"] for p in result["review_points"]], ["decision"])
        self.assertEqual(len(result["reference_images"]), 3)
        self.assertEqual(len(result["review_points"][0]["reference_images"]), 3)

    def test_blocked_hand_remains_unapproved(self):
        self.make("blocked", 2, "blocked", 1.5, blocked=True)
        result = self.export(include_decisions=True)
        self.assertEqual(result["review_points"], [])
        self.assertFalse(result["approved_for_export"])

    def test_outside_video_uses_last_frame_not_fabricated_pts(self):
        self.make(moment=7)
        result = self.export()
        self.assertEqual(len(result["review_points"]), 3)
        self.assertEqual({p["nearest_frame_index"] for p in result["review_points"]}, {29})
        self.assertEqual(len(result["reference_images"]), 2)
        self.assertTrue(all(not p["within_tolerance"] for p in result["review_points"]))

    def test_multiple_tables_deduplicates_frames(self):
        self.make("one", 1, "one", 1.5)
        self.make("two", 4, "two", 1.5)
        result = self.export(include_decisions=True)
        self.assertEqual(len(result["review_points"]), 2)
        self.assertEqual(len(result["reference_images"]), 3)

    def test_reject_source_tampering(self):
        self.make()
        other = self.root / "wrong.mp4"
        other.write_bytes(self.video.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            export(other, self.fixture.dirs, self.root / "references")
        self.assertFalse((self.root / "references").exists())

    def test_reject_existing_output_without_overwrite(self):
        self.make()
        target = self.root / "references"
        target.mkdir()
        (target / "keep.txt").write_text("do not change")
        with self.assertRaisesRegex(ValueError, "new directory"):
            self.export()
        self.assertEqual((target / "keep.txt").read_text(), "do not change")

    def test_reject_symlink_output(self):
        self.make()
        (self.root / "references").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "new directory"):
            self.export()

    def test_reject_path_traversal(self):
        self.make()
        with self.assertRaisesRegex(ValueError, "new directory"):
            export(self.video, self.fixture.dirs, self.root / ".." / "escaped")

    def test_reject_missing_ffmpeg_without_publishing(self):
        self.make(moment=1.55)
        with self.assertRaises(FileNotFoundError):
            self.export(ffmpeg="/no/such/ffmpeg", tolerance_seconds=0.02)
        self.assertFalse((self.root / "references").exists())

    def test_reject_tampered_clip(self):
        folder = self.make()
        (folder / "clip.mp4").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.export()
        self.assertFalse((self.root / "references").exists())

    def test_escaped_hand_label_no_remote_resources(self):
        self.make(label='<script>alert(1)</script>', moment=1.55)
        self.export(tolerance_seconds=0.02)
        page = (self.root / "references" / "contact_sheet.html").read_text()
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("https://", page)
        self.assertIn("connect-src 'none'", page)

    def test_cli_end_to_end(self):
        self.make()
        self.assertEqual(main([str(self.video), str(self.root / "references"),
                               *map(str, self.fixture.dirs), "--include-decisions"]), 0)
        self.assertTrue((self.root / "references" / "contact_sheet.html").exists())

    def test_detect_source_change_during_extraction(self):
        self.make(moment=1.55)
        import offline_reviewed_pts_contact_sheet as module
        original = module._extract
        def mutate_source(*args, **kwargs):
            result = original(*args, **kwargs)
            self.video.write_bytes(self.video.read_bytes() + b"x")
            return result
        with patch.object(module, "_extract", side_effect=mutate_source):
            with self.assertRaisesRegex(ValueError, "Source recording changed"):
                self.export(tolerance_seconds=0.02)
        self.assertFalse((self.root / "references").exists())

    def test_reject_unexpected_stage_file(self):
        self.make(moment=1.55)
        import offline_reviewed_pts_contact_sheet as module
        original = module._extract
        def extra_file(*args, **kwargs):
            result = original(*args, **kwargs)
            (args[2] / "untracked.txt").write_text("bad")
            return result
        with patch.object(module, "_extract", side_effect=extra_file):
            with self.assertRaisesRegex(ValueError, "Unexpected staged output"):
                self.export(tolerance_seconds=0.02)
        self.assertFalse((self.root / "references").exists())

    def test_reject_nonboolean_include_decisions(self):
        self.make()
        with self.assertRaisesRegex(ValueError, "Invalid include_decisions"):
            self.export(include_decisions="yes")

    def test_reject_bad_timeout(self):
        self.make()
        with self.assertRaisesRegex(ValueError, "Invalid FFmpeg timeout"):
            self.export(timeout_seconds=0)

    def test_image_index_boundary(self):
        items = [{"nearest_frame_index": 0}, {"nearest_frame_index": 9}]
        self.assertEqual(_indices(items, 10), [0, 1, 8, 9])

    def test_reference_limit_rejects_silent_truncation(self):
        report = {"hands": [{"table_id": 1, "hand_label": "h", "variant": "PLO5",
                             "result_directory": "a", "frame_pts_checks": [
                                 {"kind": "start", "within_tolerance": False,
                                  "human_seconds": 1., "nearest_decoded_pts_seconds": 1.,
                                  "nearest_frame_index": 1, "absolute_delta_seconds": 0.}
                                 for _ in range(121)]}]}
        with self.assertRaisesRegex(ValueError, "Too many reference points"):
            _samples(report, False)


class NearestFrameLinearScanTests(unittest.TestCase):
    def fake_scan(self, pts, targets):
        points = [{"human_seconds": t, "nearest_frame_index": None,
                   "nearest_decoded_pts_seconds": None, "absolute_delta_seconds": None}
                  for t in targets]
        with patch("offline_reviewed_source_pts_audit.subprocess.run") as mocked:
            def fake(command, **kwargs):
                kwargs["stdout"].write("".join(f"{p:.6f}\n" for p in pts).encode())
                return subprocess.CompletedProcess(command, 0, b"", b"")
            mocked.side_effect = fake
            scan = _scan_pts("/tmp/unused.mp4", points, "ffprobe", 30, max(1, len(pts)))
        return scan, points

    def test_exact_ties_choose_earlier(self):
        _, points = self.fake_scan([0., 1., 2.], [.5, 1.5, 2.5, 0., 2.])
        self.assertEqual([p["nearest_frame_index"] for p in points], [0, 1, 2, 0, 2])

    def test_reject_micro_nonmonotonic_pts(self):
        with self.assertRaisesRegex(ValueError, "not monotonic"):
            self.fake_scan([0., 0.04, 0.039999], [.04])

    def test_large_synthetic_pts_matches_exhaustive_reference(self):
        pts = [i / 25 for i in range(20000)]
        targets = [i * 3.17 for i in range(125)] + [0., 799.97, 1000., 2.0]
        scan, points = self.fake_scan(pts, targets)
        self.assertEqual(scan["decoded_frames_scanned"], 20000)
        for target, item in zip(targets, points):
            # Original exhaustive implementation keeps the first frame when
            # the new distance is within 1e-9 of the previous best.
            nearest, best = None, None
            for i, value in enumerate(pts):
                distance = abs(value - target)
                if best is None or distance < best - 1e-9:
                    nearest, best = i, distance
            self.assertEqual(item["nearest_frame_index"], nearest)


if __name__ == "__main__":
    unittest.main()
