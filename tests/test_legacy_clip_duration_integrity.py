"""FFmpeg-backed regression for legacy clip duration integrity."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_analyzer.offline_clip_integrity_audit import audit_clip, digest


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class LegacyClipDurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clip = Path(self.tmp.name) / "clip.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=s=160x120:r=10", "-t", "1", "-c:v", "mpeg4",
                        str(self.clip)], check=True, timeout=30)
        self.report = {
            "clip_sha256": digest(self.clip),
            "analysis_status": "manually_selected_offline_clip",
            "automatic_clip_selection_authorized": False,
            "video_evidence_verified": False,
            "start_seconds": 0, "end_seconds": 1,
            "crop": {"width": 160, "height": 120}
        }

    def audit(self):
        Path(str(self.clip) + ".json").write_text(json.dumps(self.report), encoding="utf-8")
        return audit_clip(self.clip)

    def test_matching_duration(self):
        self.assertTrue(self.audit()["verified"])

    def test_truncated_clip_rejected(self):
        self.report["end_seconds"] = 3
        with self.assertRaisesRegex(ValueError, "duration mismatch"):
            self.audit()

    def test_overlong_clip_rejected(self):
        self.report["end_seconds"] = 0.5
        with self.assertRaisesRegex(ValueError, "duration mismatch"):
            self.audit()

    def test_tolerance(self):
        self.report["end_seconds"] = 1.2
        self.assertTrue(self.audit()["verified"])


if __name__ == "__main__":
    unittest.main()
