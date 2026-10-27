"""Synthetic-only regression tests for explicitly reviewed PTS MP4 re-export."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from offline_reviewed_pts_reexport import prepare, reexport, main

FIXTURE = Path(__file__).resolve().parents[2] / "demo" / "demo"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe") and
                     (FIXTURE / "timestamp_plan.json").is_file(),
                     "FFmpeg and external synthetic PTS review fixture required")
class ReexportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "session"
        shutil.copytree(FIXTURE, self.root)
        self.video = self.root / "synthetic_session.mp4"
        self.reference = self.root / "review_corrected/review_template.json"
        self.proposals = self.root / "proposed_corrections.json"
        self.second = self.root / "second_review.json"
        self.plan = self.root / "timestamp_plan.json"
        self.dirs = [self.root / "PLO5_results", self.root / "PLO6_results"]
        self.approval = self.root / "new_export_approval.json"
        self.output = self.root / "reexport_hand42"

    def prepare(self):
        return prepare(self.video, self.reference, self.proposals,
                       self.second, self.plan, self.dirs, "PLO5_results", self.approval)

    def approve(self):
        self.prepare()
        data = json.loads(self.approval.read_text())
        data.update(reviewer_label_claim_unverified="synthetic-reviewer",
                    reviewed_source_frames=True, reviewed_corrected_window=True,
                    reviewed_math_and_range_assumptions=True,
                    approved_for_export=True, notes="Synthetic fixture only")
        self.approval.write_text(json.dumps(data))
        return data

    def export(self):
        return reexport(self.video, self.reference, self.proposals, self.second,
                        self.plan, self.dirs, self.approval, self.output)

    def test_prepare_defaults_not_authorized(self):
        template = self.prepare()
        self.assertFalse(template["approved_for_export"])
        self.assertFalse(template["video_content_verified"])
        self.assertEqual(template["reviewed_seconds"]["decision"], 2.03)
        self.assertTrue(self.approval.exists())
        self.assertFalse(self.output.with_suffix(".mp4").exists())

    def test_real_ffmpeg_reexport_preserves_original(self):
        original = (self.root / "PLO5_results/clip.mp4").read_bytes()
        self.approve()
        result = self.export()
        self.assertEqual(result["status"], "reexported_from_human_claim_not_visual_poker_verified")
        self.assertFalse(result["monte_carlo_recomputed"])
        self.assertFalse(result["video_content_verified"])
        self.assertEqual(original, (self.root / "PLO5_results/clip.mp4").read_bytes())
        for ext in (".mp4", ".json", ".srt", ".audit.json"):
            self.assertTrue(self.output.with_suffix(ext).exists(), ext)
        report = json.loads(self.output.with_suffix(".json").read_text())
        self.assertEqual(report["decision_seconds"], 2.03)
        self.assertEqual(report["start_seconds"], 1.0)
        self.assertEqual(report["end_seconds"], 4.0)

    def test_unapproved_template_blocked(self):
        self.prepare()
        with self.assertRaises(ValueError): self.export()

    def test_each_review_flag_required(self):
        for flag in ("reviewed_source_frames", "reviewed_corrected_window",
                     "reviewed_math_and_range_assumptions"):
            with self.subTest(flag=flag):
                self.approve() if not self.approval.exists() else None
                data = json.loads(self.approval.read_text())
                data[flag] = False
                self.approval.write_text(json.dumps(data))
                with self.assertRaises(ValueError): self.export()
                data[flag] = True
                self.approval.write_text(json.dumps(data))

    def test_modified_immutable_approval_rejected(self):
        data = self.approve()
        data["reviewed_seconds"]["decision"] = 2.04
        self.approval.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.export()

    def test_extra_claim_rejected(self):
        data = self.approve()
        data["live_poker"] = True
        self.approval.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.export()

    def test_false_claim_verified_video_rejected(self):
        data = self.approve()
        data["video_content_verified"] = True
        self.approval.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.export()

    def test_tampered_timestamp_plan_rejected(self):
        self.approve()
        self.plan.write_bytes(self.plan.read_bytes() + b" ")
        with self.assertRaises(ValueError): self.export()

    def test_tampered_original_clip_rejected(self):
        self.approve()
        with (self.root / "PLO5_results/clip.mp4").open("ab") as f:
            f.write(b"tamper")
        with self.assertRaises(ValueError): self.export()

    def test_tampered_source_video_rejected(self):
        self.approve()
        with self.video.open("ab") as f: f.write(b"tamper")
        with self.assertRaises(ValueError): self.export()

    def test_no_overwrite_existing_output(self):
        self.approve()
        self.output.with_suffix(".mp4").write_bytes(b"existing")
        with self.assertRaises(ValueError): self.export()
        self.assertEqual(self.output.with_suffix(".mp4").read_bytes(), b"existing")

    def test_symlink_approval_rejected(self):
        self.approve()
        original = self.root / "original_approval.json"
        self.approval.rename(original)
        self.approval.symlink_to(original)
        with self.assertRaises(ValueError): self.export()

    def test_unknown_result_directory_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.video, self.reference, self.proposals, self.second,
                    self.plan, self.dirs, "PLO7_results", self.approval)

    def test_duplicate_json_key_rejected(self):
        self.approve()
        self.approval.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.export()

    def test_cli_prepare(self):
        self.assertEqual(main(["prepare", str(self.video), str(self.reference),
                               str(self.proposals), str(self.second), str(self.plan),
                               "PLO5_results", str(self.approval),
                               *(str(d) for d in self.dirs)]), 0)
        self.assertTrue(self.approval.exists())


if __name__ == "__main__":
    unittest.main()
