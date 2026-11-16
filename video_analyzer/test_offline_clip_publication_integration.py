"""Regression tests for the published offline clip exporter (real FFmpeg)."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_clip_export import export_clip, sha256_file, probe_duration
from offline_atomic_artifact_publish import publish_pair_no_clobber


class ClipPublicationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=20",
            "-t", "3", "-c:v", "mpeg4", str(self.source)
        ], check=True, capture_output=True, timeout=60)
        self.out = self.root / "out"
        self.plan = {
            "source_sha256": sha256_file(self.source), "table_id": 1,
            "hand_id": "synthetic-1", "start_seconds": 0.5,
            "end_seconds": 2.5, "duration_seconds": 2.0,
            "output_name": "clip.mp4", "review_status": "insufficient_data",
            "strategic_verdict_allowed": False,
        }

    def test_real_export_hash_duration_and_no_temp_leaks(self):
        result = export_clip(self.source, self.out, self.plan)
        video = self.out / "clip.mp4"
        sidecar = self.out / "clip.mp4.json"
        self.assertTrue(video.is_file())
        self.assertEqual(result, json.loads(sidecar.read_text(encoding="utf-8")))
        self.assertEqual(result["clip_sha256"], sha256_file(video))
        self.assertAlmostEqual(probe_duration(video), 2.0, delta=0.25)
        self.assertFalse(result["strategic_verdict_allowed"])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["clip.mp4", "clip.mp4.json"])

    def test_conflicting_json_during_publish_preserves_competitor(self):
        actual_publish = publish_pair_no_clobber
        def competitor(staged_video, staged_json, final_video, final_json):
            Path(final_json).write_text("competitor", encoding="utf-8")
            return actual_publish(staged_video, staged_json, final_video, final_json)
        with patch("offline_clip_export.publish_pair_no_clobber", side_effect=competitor):
            with self.assertRaises(FileExistsError):
                export_clip(self.source, self.out, self.plan)
        self.assertEqual((self.out / "clip.mp4.json").read_text(), "competitor")
        self.assertFalse((self.out / "clip.mp4").exists())
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["clip.mp4.json"])

    def test_two_distinct_exports_have_no_shared_staging(self):
        export_clip(self.source, self.out, self.plan)
        second = dict(self.plan, output_name="clip2.mp4")
        export_clip(self.source, self.out, second)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["clip.mp4", "clip.mp4.json", "clip2.mp4", "clip2.mp4.json"])
        self.assertNotEqual(sha256_file(self.out / "clip.mp4.json"),
                            sha256_file(self.out / "clip2.mp4.json"))


if __name__ == "__main__":
    unittest.main()
