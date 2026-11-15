"""Synthetic FFmpeg regression: review export -> integrity verifier."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from .offline_review_clip_export import export_review_clip
    from .offline_clip_manifest_verify import verify_clip_manifest
except ImportError:
    from offline_review_clip_export import export_review_clip
    from offline_clip_manifest_verify import verify_clip_manifest


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and FFprobe required")
class ReviewManifestIntegration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x90:rate=10:duration=3",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", "-y", str(self.source)],
                       check=True, timeout=45)
        self.clip = self.root / "clip.mp4"
        self.record = {"start_pts": 0.5, "end_pts": 1.5, "table_id": 2}

    def export(self, record=None):
        return export_review_clip(self.source, self.clip, record or self.record)

    def test_roundtrip_with_source_and_audio(self):
        manifest = self.export()
        audit = verify_clip_manifest(self.clip, source=self.source)
        self.assertTrue(audit["valid"], audit["problems"])
        self.assertTrue(audit["source_checked"])
        self.assertFalse(audit["human_review_verified"])
        self.assertEqual(manifest["evidence_gate"]["status"], "REVIEW_REQUIRED")
        streams = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
            "-of", "json", str(self.clip)], timeout=15))["streams"]
        self.assertIn("video", [s["codec_type"] for s in streams])
        self.assertIn("audio", [s["codec_type"] for s in streams])

    def test_modified_clip_rejected(self):
        self.export()
        with self.clip.open("ab") as out:
            out.write(b"tampered")
        audit = verify_clip_manifest(self.clip, source=self.source)
        self.assertFalse(audit["valid"])
        self.assertIn("clip_hash_mismatch", audit["problems"])

    def test_modified_source_rejected(self):
        self.export()
        with self.source.open("ab") as out:
            out.write(b"tampered")
        audit = verify_clip_manifest(self.clip, source=self.source)
        self.assertFalse(audit["valid"])
        self.assertIn("source_hash_mismatch", audit["problems"])

    def test_manifest_promoted_claim_rejected(self):
        self.export()
        sidecar = self.clip.with_suffix(".json")
        data = json.loads(sidecar.read_text())
        data["gto_solution"] = True
        sidecar.write_text(json.dumps(data))
        audit = verify_clip_manifest(self.clip)
        self.assertFalse(audit["valid"])
        self.assertIn("unsupported_claims", audit["problems"])

    def test_zero_rake_conditional_not_verdict(self):
        record = {**self.record, **dict.fromkeys((
            "table_verified", "hand_verified", "hero_cards_verified",
            "board_verified", "action_verified", "amounts_verified"), True),
            "ev_assumptions": {"ranges": "hypothetical", "rake": 0,
                               "future_actions": "none"}}
        manifest = self.export(record)
        self.assertEqual(manifest["evidence_gate"]["status"],
                         "APPROVED_CONDITIONAL")
        self.assertFalse(manifest["evidence_gate"]["can_label_error"])
        self.assertTrue(verify_clip_manifest(self.clip)["valid"])


if __name__ == "__main__":
    unittest.main()
