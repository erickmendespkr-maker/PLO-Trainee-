"""End-to-end synthetic ledger -> draft windows -> FFmpeg MP4 regression.

Run: python -m unittest video_analyzer.test_offline_ledger_to_mp4_integration
No real session footage is required or uploaded.
"""
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


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and FFprobe required")
class LedgerToMp4Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "session.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=6",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.source)
        ], check=True, capture_output=True)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def plan(self, hands):
        return draft_clip_windows(
            {"source_video_sha256": self.digest, "hands": hands},
            duration_s=6.0, padding_s=0.25
        )

    def test_full_pipeline_two_tables_and_manifest(self):
        plan = self.plan([
            {"table_id": 1, "start_s": 1, "end_s": 2},
            {"table_id": 2, "start_s": 2, "end_s": 3}
        ])
        result = export_draft_clips(plan, self.source, self.root / "out")
        self.assertEqual([x["status"] for x in result["clips"]],
                         ["EXPORTED_UNVERIFIED_DRAFT"] * 2)
        self.assertFalse(result["visual_accuracy_verified"])
        self.assertFalse(result["strategic_analysis_verified"])
        for i, item in enumerate(result["clips"]):
            self.assertTrue(item["visual_review_required"])
            self.assertFalse(item["strategic_analysis_verified"])
            self.assertEqual(item["source_start_s"], plan["clips"][i]["start_s"])
            self.assertEqual(item["source_end_s"], plan["clips"][i]["end_s"])
            self.assertTrue((self.root / "out" / item["filename"]).is_file())
        manifest = json.loads((self.root / "out" / "draft_export_manifest.json").read_text())
        self.assertEqual(manifest, result)
        self.assertEqual(manifest["source_video_sha256"], self.digest)

    def test_invalid_hand_does_not_export(self):
        plan = self.plan([{"table_id": 1, "start_s": 5, "end_s": 7}])
        self.assertEqual(plan["clips"][0]["status"], "REVIEW_REQUIRED")
        result = export_draft_clips(plan, self.source, self.root / "out")
        self.assertEqual(result["clips"][0]["status"], "SKIPPED_REVIEW_REQUIRED")
        self.assertEqual(list((self.root / "out").glob("*.mp4")), [])

    def test_timeline_issue_keeps_review_warning(self):
        plan = self.plan([{"table_id": 1, "start_s": 1, "end_s": 2,
                           "timeline_issue_codes": ["OVERLAP"]}])
        self.assertEqual(plan["clips"][0]["reason"], "TIMELINE_ISSUES")
        self.assertFalse(plan["clips"][0]["hand_boundaries_verified"])
        result = export_draft_clips(plan, self.source, self.root / "out")
        self.assertEqual(result["clips"][0]["status"], "EXPORTED_UNVERIFIED_DRAFT")
        self.assertTrue(result["clips"][0]["visual_review_required"])

    def test_source_tampering_is_rejected(self):
        plan = self.plan([{"table_id": 1, "start_s": 1, "end_s": 2}])
        with self.source.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            export_draft_clips(plan, self.source, self.root / "out")

    def test_padding_clamped_at_video_boundaries(self):
        plan = self.plan([{"table_id": 1, "start_s": 0, "end_s": 0.5},
                          {"table_id": 2, "start_s": 5.5, "end_s": 6}])
        self.assertEqual(plan["clips"][0]["start_s"], 0)
        self.assertEqual(plan["clips"][1]["end_s"], 6)
        result = export_draft_clips(plan, self.source, self.root / "out")
        self.assertEqual(len([x for x in result["clips"]
                              if x["status"] == "EXPORTED_UNVERIFIED_DRAFT"]), 2)


if __name__ == "__main__":
    unittest.main()
