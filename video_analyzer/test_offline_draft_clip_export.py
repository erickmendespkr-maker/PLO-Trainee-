"""Synthetic FFmpeg integration regression tests for unverified draft export."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .offline_draft_clip_export import export_draft_clips
except ImportError:
    from offline_draft_clip_export import export_draft_clips


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class DraftExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x120:r=10:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.source)], check=True)
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.plan = {"source_video_sha256": self.sha, "video_duration_s": 3, "exported": False, "clips": [{"status": "DRAFT_REVIEW_ONLY", "start_s": 0.5, "end_s": 2.5}, {"status": "REVIEW_REQUIRED"}]}

    def test_export_and_manifest(self):
        result = export_draft_clips(self.plan, self.source, self.root / "out")
        self.assertEqual(result["clips"][0]["status"], "EXPORTED_UNVERIFIED_DRAFT")
        self.assertEqual(result["clips"][1]["status"], "SKIPPED_REVIEW_REQUIRED")
        self.assertFalse(result["strategic_analysis_verified"])
        self.assertTrue((self.root / "out" / "draft_hand_0000.mp4").is_file())
        self.assertEqual(json.loads((self.root / "out" / "draft_export_manifest.json").read_text())["clips"], result["clips"])

    def test_bad_sha_rejected(self):
        self.plan["source_video_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            export_draft_clips(self.plan, self.source, self.root / "out")

    def test_invalid_interval_skipped(self):
        self.plan["clips"][0]["end_s"] = 5
        result = export_draft_clips(self.plan, self.source, self.root / "out")
        self.assertEqual(result["clips"][0]["status"], "SKIPPED_INVALID_INTERVAL")

    def test_nonempty_output_rejected(self):
        out = self.root / "out"
        out.mkdir()
        (out / "existing").write_text("keep")
        with self.assertRaises(FileExistsError):
            export_draft_clips(self.plan, self.source, out)
        self.assertEqual((out / "existing").read_text(), "keep")

    def test_duration_mismatch_rejected(self):
        self.plan["video_duration_s"] = 20
        with self.assertRaises(ValueError):
            export_draft_clips(self.plan, self.source, self.root / "out")


if __name__ == "__main__":
    unittest.main()
