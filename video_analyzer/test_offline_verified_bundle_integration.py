"""Integration regression: real FFmpeg + real JSON + real integrity audit.

Run: python -m unittest video_analyzer.test_offline_verified_bundle_integration -v
Only synthetic media; no real session or private video is required.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .offline_verified_bundle import export_and_verify_bundle
    from .offline_bundle_integrity import verify_bundle
except ImportError:
    from offline_verified_bundle import export_and_verify_bundle
    from offline_bundle_integrity import verify_bundle


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and FFprobe required for real integration")
class VerifiedBundleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10",
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(self.source)
        ], check=True, capture_output=True)

    def _analysis(self):
        # Intentionally insufficient strategic evidence: alignment is not
        # permission to claim an observed poker decision or valid EV.
        return {"start_s": 0.5, "end_s": 2.5,
                "status": "INSUFFICIENT_DATA",
                "evidence": {"status": "INSUFFICIENT_DATA",
                             "missing_fields": ["hero_cards", "board", "action"],
                             "invalid_fields": [], "unverified_fields": []}}

    def test_real_export_and_audit(self):
        dest = self.root / "clip.mp4"
        result = export_and_verify_bundle(
            self.source, dest, self._analysis(),
            clip_start_s=0.25, clip_end_s=2.75)
        self.assertEqual(result["status"], "EXPORTED_INTEGRITY_OK_TEMPORAL_ONLY")
        self.assertFalse(result["visual_verification"])
        self.assertFalse(result["strategic_verification"])
        self.assertTrue(dest.is_file())
        report = json.loads(dest.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertFalse(report["clip"]["visually_verified"])
        self.assertEqual(verify_bundle(dest)["status"], "INTEGRITY_OK_TEMPORAL_ONLY")

    def test_mutated_mp4_fails_integrity_without_deletion(self):
        dest = self.root / "clip.mp4"
        export_and_verify_bundle(self.source, dest, self._analysis(),
                                 clip_start_s=0.25, clip_end_s=2.75)
        with dest.open("ab") as stream:
            stream.write(b"modified after export")
        result = verify_bundle(dest)
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("clip_hash_mismatch", result["problems"])
        self.assertTrue(dest.with_suffix(".json").exists())

    def test_preexisting_report_is_preserved(self):
        dest = self.root / "clip.mp4"
        report = dest.with_suffix(".json")
        report.write_text("owned by another process", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            export_and_verify_bundle(self.source, dest, self._analysis(),
                                     clip_start_s=0.25, clip_end_s=2.75)
        self.assertEqual(report.read_text(encoding="utf-8"),
                         "owned by another process")
        self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
