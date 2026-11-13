"""FFmpeg-backed synthetic tests for the conservative MP4 auditor."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_clip_evidence_manifest import clip_manifest, clip_sha256
from offline_clip_ffprobe_audit import audit_clip


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
class ClipProbeAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "clip.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=2", "-c:v", "mpeg4", "-y", str(self.path)], check=True)
        identity = dict(hand_id="h1", table_id=1, video_sha256="a"*64, start_seconds=4., end_seconds=5.)
        self.manifest = clip_manifest(self.path, identity, 10, 3, 5)

    def test_valid_clip_decodes_without_claiming_visual_truth(self):
        result = audit_clip(self.manifest, self.path)
        self.assertEqual(result["status"], "CONTAINER_AND_DECODE_VERIFIED_ONLY")
        self.assertFalse(result["approved_for_publication"])
        self.assertFalse(result["source_timeline_verified"])
        self.assertEqual(result["video_width"], 160)

    def test_tampered_file_rejected(self):
        self.path.write_bytes(self.path.read_bytes() + b"extra")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit_clip(self.manifest, self.path)

    def test_wrong_duration_rejected(self):
        self.manifest["clip"]["end_seconds"] = 4.1
        with self.assertRaisesRegex(ValueError, "duration differs"):
            audit_clip(self.manifest, self.path)

    def test_unapproved_manifest_required(self):
        self.manifest["approved_for_publication"] = True
        with self.assertRaises(ValueError):
            audit_clip(self.manifest, self.path)

    def test_invalid_tolerance_rejected(self):
        with self.assertRaises(ValueError):
            audit_clip(self.manifest, self.path, tolerance_seconds=float("nan"))

    def test_invalid_video_rejected(self):
        self.path.write_text("not a video")
        self.manifest["clip"]["sha256"] = clip_sha256(self.path)
        with self.assertRaisesRegex(ValueError, "ffprobe failed"):
            audit_clip(self.manifest, self.path)


if __name__ == "__main__":
    unittest.main()
