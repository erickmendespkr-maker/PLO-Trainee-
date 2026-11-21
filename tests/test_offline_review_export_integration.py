"""Integration regression for the existing offline export + audit pipeline.

Run: python -m unittest discover -s tests -p 'test_offline_review_export_integration.py'
Requires ffmpeg and ffprobe on PATH; uses only synthetic local footage.
"""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_analyzer.offline_review_clip_export import export_review_clip
from video_analyzer.offline_review_export_audit import audit_review_export


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "ffmpeg/ffprobe not installed")
class OfflineReviewExportIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10",
            "-t", "3", "-c:v", "mpeg4", str(self.source)
        ], check=True, capture_output=True, timeout=30)
        self.destination = self.root / "review.mp4"
        self.record = {"table_id": 1, "start_pts": 0.5, "end_pts": 1.5}

    def export(self):
        return export_review_clip(self.source, self.destination, self.record)

    def test_export_and_audit_real_ffmpeg(self):
        manifest = self.export()
        self.assertEqual(manifest["requested_interval_seconds"], [0.5, 1.5])
        result = audit_review_export(self.destination, source=self.source)
        self.assertTrue(result["integrity_verified"])
        self.assertTrue(result["source_checked"])
        self.assertFalse(result["hand_verified"])
        self.assertFalse(result["strategic_analysis_verified"])

    def test_tampered_manifest_is_rejected(self):
        self.export()
        sidecar = self.destination.with_suffix(".json")
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        manifest["requested_interval_seconds"] = [0.5, 2.5]
        sidecar.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            audit_review_export(self.destination, source=self.source)

    def test_tampered_explanation_is_rejected(self):
        self.export()
        sidecar = self.destination.with_suffix(".json")
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        manifest["explanation"] = "This hand is a proven GTO error."
        sidecar.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unverified clip explanation"):
            audit_review_export(self.destination, source=self.source)

    def test_malformed_source_digest_is_rejected_without_source(self):
        self.export()
        sidecar = self.destination.with_suffix(".json")
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        manifest["source_sha256"] = "not-a-digest"
        sidecar.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
            audit_review_export(self.destination)

    def test_tampered_clip_is_rejected(self):
        self.export()
        with self.destination.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaises(ValueError):
            audit_review_export(self.destination, source=self.source)

    def test_duplicate_destination_does_not_overwrite(self):
        self.export()
        original = self.destination.read_bytes()
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual(self.destination.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
