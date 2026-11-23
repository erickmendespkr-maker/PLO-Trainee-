"""Regression checks for audit provenance on non-exported clip candidates."""
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
class DraftAuditProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                        "-i", "color=size=64x64:rate=10:duration=2", "-c:v",
                        "libx264", "-pix_fmt", "yuv420p", str(self.source)],
                       check=True, capture_output=True)
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def export(self, clips):
        plan = {"exported": False, "source_video_sha256": self.sha,
                "video_duration_s": 2.0, "clips": clips}
        return export_draft_clips(plan, self.source, self.root / "out")

    def test_skipped_review_preserves_provenance(self):
        result = self.export([{"hand_index": 42, "table_id": 3,
                              "timeline_issue_codes": ["OVERLAP"],
                              "reason": "TIMELINE_ISSUES", "status": "REVIEW_REQUIRED"}])
        item = result["clips"][0]
        self.assertEqual(item["status"], "SKIPPED_REVIEW_REQUIRED")
        self.assertEqual(item["hand_index"], 42)
        self.assertEqual(item["table_id"], 3)
        self.assertEqual(item["timeline_issue_codes"], ["OVERLAP"])
        self.assertEqual(item["draft_reason"], "TIMELINE_ISSUES")
        self.assertEqual(json.loads((self.root / "out" / "draft_export_manifest.json").read_text()), result)

    def test_invalid_interval_preserves_provenance(self):
        result = self.export([{"hand_index": 9, "table_id": 2,
                              "timeline_issue_codes": ["OUTSIDE_VIDEO"],
                              "reason": "TIMELINE_ISSUES", "status": "DRAFT_REVIEW_ONLY",
                              "start_s": 1, "end_s": 9}])
        item = result["clips"][0]
        self.assertEqual(item["status"], "SKIPPED_INVALID_INTERVAL")
        self.assertEqual(item["hand_index"], 9)
        self.assertEqual(item["table_id"], 2)
        self.assertEqual(item["timeline_issue_codes"], ["OUTSIDE_VIDEO"])

    def test_non_dict_candidate_is_safe(self):
        result = self.export([None])
        self.assertEqual(result["clips"][0]["status"], "SKIPPED_REVIEW_REQUIRED")
        self.assertEqual(result["clips"][0]["draft_reason"], "INVALID_CLIP")


if __name__ == "__main__":
    unittest.main()
