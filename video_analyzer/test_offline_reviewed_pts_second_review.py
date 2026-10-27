"""Synthetic offline tests for second-stage timestamp review; no real poker OCR."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from offline_reviewed_pts_second_review import (
    REVIEW_STATUS, PLAN_STATUS, prepare, build_plan, finalize, main,
)

FIXTURE = Path(__file__).resolve().parents[2] / "demo"


@unittest.skipUnless(shutil.which("ffprobe") and FIXTURE.exists(),
                     "FFprobe and synthetic fixture required")
class SecondReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(FIXTURE / "synthetic_session.mp4", self.root)
        shutil.copy2(FIXTURE / "proposed_corrections.json", self.root)
        for name in ("PLO5_results", "PLO6_results", "review_corrected"):
            shutil.copytree(FIXTURE / name, self.root / name)
        self.video = self.root / "synthetic_session.mp4"
        self.reference = self.root / "review_corrected" / "review_template.json"
        self.proposals = self.root / "proposed_corrections.json"
        self.directories = [self.root / "PLO5_results", self.root / "PLO6_results"]
        self.review = self.root / "second_review.json"
        self.plan = self.root / "timestamp_plan.json"

    def prepare(self):
        return prepare(self.video, self.reference, self.proposals,
                       self.directories, self.review)

    def edit(self, **fields):
        data = json.loads(self.review.read_text())
        data.update(fields)
        self.review.write_text(json.dumps(data, ensure_ascii=False))
        return data

    def approve(self):
        data = json.loads(self.review.read_text())
        data.update(reviewer_label="synthetic-reviewer", reviewed_source_frames=True,
                    reviewed_clip_windows=True, reviewed_math_provenance=True)
        data["decisions"][0]["accept_correction"] = True
        data["decisions"][0]["review_notes"] = "Quadro sintético revisto"
        self.review.write_text(json.dumps(data, ensure_ascii=False))
        return data

    def plan_result(self):
        return build_plan(self.video, self.reference, self.proposals,
                          self.review, self.directories)

    def test_prepare_unapproved_template(self):
        template = self.prepare()
        self.assertEqual(template["status"], REVIEW_STATUS)
        self.assertEqual(len(template["decisions"]), 1)
        self.assertFalse(template["approved_for_export"])
        self.assertFalse(template["decisions"][0]["accept_correction"])

    def test_valid_review_yields_non_exportable_plan(self):
        self.prepare()
        self.approve()
        result = finalize(self.video, self.reference, self.proposals,
                          self.review, self.directories, self.plan)
        self.assertEqual(result["status"], PLAN_STATUS)
        self.assertEqual(result["reviewed_hand_count"], 1)
        self.assertFalse(result["approved_for_export"])
        self.assertFalse(result["automatic_clip_selection_authorized"])
        self.assertFalse(result["math_recomputed"])
        hand = result["reviewed_windows"][0]
        self.assertEqual(hand["original_seconds"]["decision"], 2.0)
        self.assertAlmostEqual(hand["reviewed_seconds"]["decision"], 2.03)
        self.assertEqual(hand["original_seconds"]["start"], 1.0)
        self.assertEqual(hand["original_seconds"]["end"], 4.0)
        self.assertTrue(self.plan.is_file())

    def test_rejected_correction_keeps_no_plan(self):
        self.prepare()
        result = self.plan_result()
        self.assertEqual(result["reviewed_hand_count"], 0)
        self.assertEqual(result["rejected_or_deferred_correction_count"], 1)
        self.assertEqual(result["reviewed_windows"], [])

    def test_approval_requires_reviewer_label(self):
        self.prepare()
        self.approve()
        self.edit(reviewer_label="")
        with self.assertRaises(ValueError): self.plan_result()

    def test_approval_requires_three_review_checks(self):
        for missing in ("reviewed_source_frames", "reviewed_clip_windows",
                        "reviewed_math_provenance"):
            with self.subTest(missing=missing):
                if self.review.exists(): self.review.unlink()
                self.prepare()
                self.approve()
                self.edit(**{missing: False})
                with self.assertRaises(ValueError): self.plan_result()

    def test_review_flags_must_be_boolean(self):
        self.prepare()
        self.edit(reviewed_source_frames=1)
        with self.assertRaises(ValueError): self.plan_result()

    def test_reviewed_evidence_immutable(self):
        self.prepare()
        data = json.loads(self.review.read_text())
        data["decisions"][0]["proposed_seconds"] = 1.99
        self.review.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.plan_result()

    def test_review_cannot_change_source_hash(self):
        self.prepare()
        self.edit(source_recording_sha256_verified_bytes="0" * 64)
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_extra_review_fields(self):
        self.prepare()
        self.edit(allow_live_poker=True)
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_modified_proposal_report(self):
        self.prepare()
        data = json.loads(self.proposals.read_text())
        data["corrections"][0]["proposed_seconds"] = 2.04
        self.proposals.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_modified_source_video(self):
        self.prepare()
        with self.video.open("ab") as f: f.write(b"tampered")
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_modified_reference_jpeg(self):
        self.prepare()
        image = self.root / "review_corrected" / "frame_0001.jpg"
        image.write_bytes(image.read_bytes() + b"tampered")
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_modified_pipeline_manifest(self):
        self.prepare()
        manifest = self.root / "PLO5_results" / "pipeline.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_duplicate_json_keys(self):
        self.prepare()
        raw = self.review.read_text()
        self.review.write_text('{"schema_version":1,"schema_version":2}')
        with self.assertRaises(ValueError): self.plan_result()
        self.review.write_text(raw)

    def test_no_overwrite_existing_plan(self):
        self.prepare()
        self.approve()
        self.plan.write_text("do not overwrite")
        with self.assertRaises(ValueError):
            finalize(self.video, self.reference, self.proposals,
                     self.review, self.directories, self.plan)
        self.assertEqual(self.plan.read_text(), "do not overwrite")

    def test_no_output_when_validation_fails(self):
        self.prepare()
        self.approve()
        self.edit(reviewer_label="bad\nlabel")
        with self.assertRaises(ValueError):
            finalize(self.video, self.reference, self.proposals,
                     self.review, self.directories, self.plan)
        self.assertFalse(self.plan.exists())

    def test_reject_symlink_second_review(self):
        self.prepare()
        other = self.root / "other.json"
        self.review.rename(other)
        self.review.symlink_to(other)
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_oversized_notes(self):
        self.prepare()
        data = self.approve()
        data["decisions"][0]["review_notes"] = "x" * 501
        self.review.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.plan_result()

    def test_reject_window_expansion_even_if_proposal_verified(self):
        self.prepare()
        self.approve()
        # This test isolates the final clip-boundary invariant. The earlier
        # proposal validator does not authorize expanding original clips.
        original_build = __import__("offline_reviewed_pts_second_review").build_index
        def widened(_directories):
            index = original_build(_directories)
            for hand in index["hands"]:
                if hand["result_directory"] == "PLO5_results":
                    hand["clip_start_seconds_human"] = 2.05
            return index
        with patch("offline_reviewed_pts_second_review.build_index", side_effect=widened):
            with self.assertRaises(ValueError): self.plan_result()

    def test_cli_prepare_and_finalize(self):
        self.assertEqual(main(["prepare", str(self.video), str(self.reference),
                               str(self.proposals), str(self.review),
                               *(str(d) for d in self.directories)]), 0)
        self.approve()
        self.assertEqual(main(["finalize", str(self.video), str(self.reference),
                               str(self.proposals), str(self.review), str(self.plan),
                               *(str(d) for d in self.directories)]), 0)
        self.assertTrue(self.plan.exists())


if __name__ == "__main__":
    unittest.main()
