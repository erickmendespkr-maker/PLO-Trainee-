"""Real FFmpeg integration tests for trusted offline review binding.

No private footage, network access, or live poker integration.
Run: python -m unittest video_analyzer/test_offline_review_binding_integration.py
from the video_analyzer directory (or with PYTHONPATH=video_analyzer).
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_clip_export import export_clip
from offline_review_binding import audit_against_review


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe required")
class RealReviewBindingIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
            "-t", "2", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(self.source)
        ], check=True, capture_output=True, timeout=30)
        self.review = {
            "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "hand_id": "synthetic-h1", "table_id": 1,
            "start_seconds": 0.0, "end_seconds": 1.0,
            "review_status": "insufficient_data",
        }
        plan = {
            **self.review, "duration_seconds": 1.0,
            "output_name": "synthetic-clip.mp4",
            "strategic_verdict_allowed": False,
        }
        self.clip = self.root / "output" / plan["output_name"]
        export_clip(self.source, self.clip.parent, plan)

    def test_integrated_binding_and_provenance(self):
        result = audit_against_review(self.clip, self.review)
        self.assertTrue(result["integrity_verified"])
        self.assertTrue(result["trusted_review_binding_verified"])
        self.assertFalse(result["strategic_error_established"])
        self.assertFalse(result["hand_reconstruction_verified"])

    def test_wrong_hand_rejected(self):
        changed = {**self.review, "hand_id": "different-hand"}
        with self.assertRaisesRegex(ValueError, "hand identity mismatch"):
            audit_against_review(self.clip, changed)

    def test_wrong_table_rejected(self):
        changed = {**self.review, "table_id": 2}
        with self.assertRaisesRegex(ValueError, "table identity mismatch"):
            audit_against_review(self.clip, changed)

    def test_wrong_interval_rejected(self):
        changed = {**self.review, "start_seconds": 0.1}
        with self.assertRaisesRegex(ValueError, "source interval mismatch"):
            audit_against_review(self.clip, changed)

    def test_unreviewed_promotion_rejected(self):
        changed = {**self.review, "review_status": "confirmed"}
        with self.assertRaisesRegex(ValueError, "review status mismatch"):
            audit_against_review(self.clip, changed)

    def test_sidecar_tampering_rejected(self):
        sidecar = self.clip.with_name(self.clip.name + ".json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["hand_id"] = "other-hand"
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hand identity mismatch"):
            audit_against_review(self.clip, self.review)

    def test_mp4_tampering_rejected(self):
        with self.clip.open("ab") as output:
            output.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "clip hash mismatch"):
            audit_against_review(self.clip, self.review)


if __name__ == "__main__":
    unittest.main()
