"""Offline synthetic regression tests; never validates poker visual content."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from offline_reviewed_pts_correction_import import build_corrections, export, main

FIXTURE = Path(__file__).resolve().parents[2] / "demo" / "demo"


@unittest.skipUnless(shutil.which("ffprobe") and FIXTURE.exists(),
                     "FFprobe and synthetic fixtures required")
class CorrectionImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("synthetic_session.mp4",):
            shutil.copy2(FIXTURE / name, self.root / name)
        for name in ("PLO5_results", "PLO6_results", "reference_review"):
            shutil.copytree(FIXTURE / name, self.root / name)
        self.source = self.root / "synthetic_session.mp4"
        self.template = self.root / "reference_review" / "review_template.json"
        self.directories = [self.root / "PLO5_results", self.root / "PLO6_results"]
        self.output = self.root / "proposals.json"

    def read(self):
        return json.loads(self.template.read_text())

    def write(self, payload):
        self.template.write_text(json.dumps(payload, allow_nan=True))

    def run_import(self):
        return build_corrections(self.source, self.template, self.directories)

    def change(self, point=0, seconds=2.0, approved=True):
        payload = self.read()
        payload["review_points"][point]["corrected_seconds"] = seconds
        payload["review_points"][point]["approved_by_human"] = approved
        self.write(payload)

    def test_unedited_template_produces_unapproved_empty_report(self):
        result = self.run_import()
        self.assertEqual(result["proposed_correction_count"], 0)
        self.assertFalse(result["approved_for_export"])
        self.assertFalse(result["video_content_verified"])

    def test_valid_human_correction_snaps_to_decoded_frame(self):
        self.change(seconds=2.03)
        result = self.run_import()
        self.assertEqual(result["proposed_correction_count"], 1)
        self.assertEqual(result["corrections"][0]["nearest_decoded_pts_seconds"], 2.0)
        self.assertEqual(result["corrections"][0]["nearest_frame_index"], 20)
        self.assertFalse(result["automatic_clip_selection_authorized"])

    def test_two_tables_can_have_distinct_proposals(self):
        self.change(0, 2.01)
        self.change(1, 2.04)
        self.assertEqual(self.run_import()["proposed_correction_count"], 2)

    def test_export_creates_new_json_without_touching_source(self):
        original = self.source.read_bytes()
        result = export(self.source, self.template, self.directories, self.output)
        self.assertEqual(json.loads(self.output.read_text())["status"], result["status"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_export_refuses_existing_file(self):
        self.output.write_text("preserve")
        with self.assertRaises(ValueError):
            export(self.source, self.template, self.directories, self.output)
        self.assertEqual(self.output.read_text(), "preserve")

    def test_export_refuses_other_parent(self):
        with self.assertRaises(ValueError):
            export(self.source, self.template, self.directories,
                   self.root / "reference_review" / "new.json")

    def test_reject_approved_for_export(self):
        payload = self.read(); payload["approved_for_export"] = True; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_content_verified_claim(self):
        payload = self.read(); payload["video_content_verified"] = True; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_unapproved_nonnull_correction(self):
        self.change(seconds=2.0, approved=False)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_approval_without_correction(self):
        payload = self.read(); payload["review_points"][0]["approved_by_human"] = True; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_boolean_timestamp(self):
        self.change(seconds=True)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_negative_timestamp(self):
        self.change(seconds=-1)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_nan(self):
        self.change(seconds=float("nan"))
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_shift_exceeding_max(self):
        self.change(seconds=9.0)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_correction_outside_clip_window(self):
        self.change(seconds=0.0)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_modified_original_timestamp(self):
        payload = self.read(); payload["review_points"][0]["original_human_seconds"] = 1.0; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_modified_nearest_frame_index(self):
        payload = self.read(); payload["review_points"][0]["nearest_frame_index"] = 1; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_modified_reference_list(self):
        payload = self.read(); payload["review_points"][0]["reference_images"] = []; self.write(payload)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_tampered_jpeg(self):
        (self.root / "reference_review" / "frame_0001.jpg").write_bytes(b"fake")
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_tampered_source(self):
        with self.source.open("ab") as stream: stream.write(b"extra")
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_tampered_pipeline(self):
        (self.root / "PLO5_results" / "math.json").write_text("{}")
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_duplicate_json_keys(self):
        raw = self.template.read_text()
        self.template.write_text(raw.replace('"schema_version": 1,',
                                             '"schema_version": 1, "schema_version": 1,', 1))
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_symlink_reference(self):
        image = self.root / "reference_review" / "frame_0000.jpg"
        image.unlink(); image.symlink_to(self.source)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_symlink_template(self):
        raw = self.template.read_bytes()
        self.template.unlink()
        other = self.root / "copy.json"; other.write_bytes(raw)
        self.template.symlink_to(other)
        with self.assertRaises(ValueError): self.run_import()

    def test_reject_extra_reference_file(self):
        (self.root / "reference_review" / "extra.txt").write_text("unexpected")
        with self.assertRaises(ValueError): self.run_import()

    def test_cli_smoke(self):
        code = main([str(self.source), str(self.template), str(self.output),
                     *(str(d) for d in self.directories)])
        self.assertEqual(code, 0)
        self.assertTrue(self.output.is_file())

    def test_no_output_when_validation_fails(self):
        self.change(seconds=100)
        with self.assertRaises(ValueError):
            export(self.source, self.template, self.directories, self.output)
        self.assertFalse(self.output.exists())

    def test_corrected_pts_gap_rejected(self):
        # A proposed time can be within the old clip window but not near any
        # decoded frame when a strict source-frame proximity check is applied.
        self.change(seconds=2.04)
        with patch("offline_reviewed_pts_correction_import.MAX_SNAP_SECONDS", 0.01):
            with self.assertRaises(ValueError): self.run_import()

    def test_reject_mixed_pipeline_parent(self):
        with self.assertRaises(ValueError):
            build_corrections(self.source, self.template,
                              [self.directories[0], self.root])


if __name__ == "__main__":
    unittest.main()
