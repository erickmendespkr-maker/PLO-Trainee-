"""Regression: exported draft clips must retain source hand and review provenance."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .offline_ledger_clip_drafts import draft_clip_windows
    from .offline_draft_clip_export import export_draft_clips
except ImportError:
    from offline_ledger_clip_drafts import draft_clip_windows
    from offline_draft_clip_export import export_draft_clips


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class DraftManifestProvenance(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "sample.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=128x96:rate=10:duration=4",
                        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(self.source)], check=True, capture_output=True)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_export_retains_hand_identity_and_timeline_warnings(self):
        ledger = {"source_video_sha256": self.digest, "hands": [
            {"table_id": 1, "start_s": 0.5, "end_s": 1.0,
             "timeline_issue_codes": ["OVERLAP"]},
            {"table_id": 2, "start_s": 2.0, "end_s": 3.0}
        ]}
        plan = draft_clip_windows(ledger, duration_s=4, padding_s=0.1)
        result = export_draft_clips(plan, self.source, self.root / "out")
        first, second = result["clips"]
        self.assertEqual(first["hand_index"], 0)
        self.assertEqual(first["table_id"], 1)
        self.assertEqual(first["timeline_issue_codes"], ["OVERLAP"])
        self.assertEqual(first["draft_reason"], "TIMELINE_ISSUES")
        self.assertEqual(second["hand_index"], 1)
        self.assertEqual(second["table_id"], 2)
        self.assertEqual(second["timeline_issue_codes"], [])
        self.assertTrue(first["visual_review_required"])
        self.assertFalse(first["strategic_analysis_verified"])
        saved = json.loads((self.root / "out" / "draft_export_manifest.json").read_text())
        self.assertEqual(saved, result)

    def test_skipped_entry_retains_original_hand_index(self):
        ledger = {"source_video_sha256": self.digest, "hands": [
            {"table_id": 1, "start_s": 0.5, "end_s": 1.0},
            {"table_id": 2, "start_s": 3.0, "end_s": 5.0}
        ]}
        plan = draft_clip_windows(ledger, duration_s=4)
        result = export_draft_clips(plan, self.source, self.root / "out")
        self.assertEqual(result["clips"][1]["status"], "SKIPPED_REVIEW_REQUIRED")
        self.assertEqual(result["clips"][1]["hand_index"], 1)


if __name__ == "__main__":
    unittest.main()
