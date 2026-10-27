"""Offline synthetic provenance/validation tests for incomplete hand candidates."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from offline_four_table_sample_review import build as sample_build
from offline_four_table_ocr_proposals import scan as ocr_scan
import tempfile
import unittest

from offline_four_table_ocr_human_review import review
from offline_four_table_hand_candidates import build

class HandCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / "synthetic.mp4"
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not Path(font).is_file():
            raise RuntimeError("Test font unavailable")
        labels = [("POT 120", 16, 32), ("STACK 80", 336, 32),
                  ("CALL 20", 16, 220), ("As Kd Qh", 336, 220)]
        filters = ",".join(f"drawtext=fontfile={font}:text='{label}':fontcolor=black:"
                           f"fontsize=30:x={x}:y={y}" for label, x, y in labels)
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=white:s=640x360:r=3:d=2",
                        "-vf", filters, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-y", str(cls.video)], check=True, capture_output=True, timeout=30)
        layout = cls.root / "layout.json"
        layout.write_text(json.dumps({"schema_version": 1, "layout": "grid",
                                      "rows": 2, "columns": 2}))
        cls.bundle = cls.root / "bundle"
        sample_build(cls.video, layout, cls.bundle, [0.4])
        source_sha = hashlib.sha256((cls.bundle / "region_samples.json").read_bytes()).hexdigest()
        roi = cls.root / "roi.json"
        roi.write_text(json.dumps({"schema_version": 1,
                                   "source_manifest_sha256": source_sha,
                                   "tasks": [
                                       {"table_id": i, "sample_index": 0,
                                        "field": field,
                                        "roi": {"x": 0, "y": 0, "width": 310,
                                                "height": 160}}
                                       for i, field in enumerate(
                                           ("pot", "stack", "action", "board"), 1)]}))
        cls.ocr = cls.root / "ocr.json"
        ocr_scan(cls.bundle, roi, cls.ocr, recording_path=cls.video)
        cls.decisions = cls.root / "decisions.json"
        candidates = json.loads(cls.ocr.read_text())["candidates"]
        values = {"pot": "120", "stack": "80", "action": "call", "board": "As Kd Qh"}
        cls.decisions.write_text(json.dumps({"schema_version": 1,
            "source_ocr_sha256": hashlib.sha256(cls.ocr.read_bytes()).hexdigest(),
            "decisions": [{"candidate_index": i, "decision": "correct",
                           "reviewed_text": values[c["field"]],
                           "visual_evidence_checked": True, "note": "synthetic"}
                          for i, c in enumerate(candidates)]}))
        cls.reviewed = cls.root / "reviewed.json"
        review(cls.bundle, cls.ocr, cls.decisions, cls.reviewed, recording_path=cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root_tmp = Path(self.tmp.name)
        self.out = self.root_tmp / "hands.json"
        self.manifest_path = self.root_tmp / "windows.json"
        self.manifest = {
            "schema_version": 1,
            "source_reviewed_fields_sha256": hashlib.sha256(self.reviewed.read_bytes()).hexdigest(),
            "hands": [
                {"hand_id": "t1h1", "table_id": 1, "game_type": "PLO5",
                 "start_pts_seconds": 0.0, "end_pts_seconds": 1.5,
                 "boundaries_visually_checked": True, "observation_indices": [0]},
                {"hand_id": "t4h1", "table_id": 4, "game_type": "PLO6",
                 "start_pts_seconds": 0.0, "end_pts_seconds": 1.5,
                 "boundaries_visually_checked": True, "observation_indices": [3]},
            ]}
        self.write()

    def write(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def run_build(self, **kw):
        return build(kw.get("bundle", self.bundle), kw.get("ocr", self.ocr),
                     kw.get("decisions", self.decisions), kw.get("reviewed", self.reviewed),
                     self.manifest_path, self.out, recording_path=kw.get("video", self.video))

    def invalid(self, **kw):
        self.write()
        with self.assertRaises((ValueError, FileExistsError)):
            self.run_build(**kw)
        self.assertFalse(self.out.exists())

    def test_real_synthetic_lineage_and_no_math_promotion(self):
        result = self.run_build()
        self.assertEqual(len(result["hands"]), 2)
        self.assertEqual(result["hands"][0]["observations"][0]["value"], "120")
        self.assertFalse(result["complete_hand_reconstructed"])
        self.assertFalse(result["ready_for_equity_or_ev"])
        self.assertFalse(result["automatic_clip_selection_authorized"])
        self.assertEqual(json.loads(self.out.read_text()), result)

    def test_missing_fields_are_explicit(self):
        result = self.run_build()
        self.assertIn("hero_cards", result["hands"][0]["missing_observed_fields"])
        self.assertIn("action", result["hands"][1]["missing_observed_fields"])

    def test_review_hash_mismatch(self):
        self.manifest["source_reviewed_fields_sha256"] = "0" * 64
        self.invalid()

    def test_duplicate_hand_id(self):
        self.manifest["hands"][1]["hand_id"] = "t1h1"
        self.invalid()

    def test_wrong_table(self):
        self.manifest["hands"][0]["table_id"] = 3
        self.invalid()

    def test_bool_table_id(self):
        self.manifest["hands"][0]["table_id"] = True
        self.invalid()

    def test_wrong_game_type(self):
        self.manifest["hands"][0]["game_type"] = "PLO4"
        self.invalid()

    def test_boundary_requires_review(self):
        self.manifest["hands"][0]["boundaries_visually_checked"] = False
        self.invalid()

    def test_nonfinite_window_rejected(self):
        self.manifest["hands"][0]["end_pts_seconds"] = float("nan")
        self.invalid()

    def test_outside_duration(self):
        self.manifest["hands"][0]["end_pts_seconds"] = 999
        self.invalid()

    def test_outside_window(self):
        self.manifest["hands"][0]["start_pts_seconds"] = 1.2
        self.invalid()

    def test_duplicate_observation_in_hand(self):
        self.manifest["hands"][0]["observation_indices"] = [0, 0]
        self.invalid()

    def test_observation_reused_across_hands(self):
        self.manifest["hands"][1]["table_id"] = 1
        self.manifest["hands"][1]["observation_indices"] = [0]
        self.invalid()

    def test_overlapping_hands_same_table(self):
        self.manifest["hands"][1]["table_id"] = 1
        self.manifest["hands"][1]["start_pts_seconds"] = 0.5
        self.manifest["hands"][1]["observation_indices"] = [0]
        self.invalid()

    def test_unsorted_indices(self):
        self.manifest["hands"][0]["observation_indices"] = [3, 0]
        self.invalid()

    def test_invalid_index(self):
        self.manifest["hands"][0]["observation_indices"] = [999]
        self.invalid()

    def test_extra_authorize_flag_rejected(self):
        self.manifest["hands"][0]["authorize_equity"] = True
        self.invalid()

    def test_existing_output_preserved(self):
        self.out.write_text("keep")
        with self.assertRaises(ValueError):
            self.run_build()
        self.assertEqual(self.out.read_text(), "keep")

    def test_symlink_manifest_rejected(self):
        real = self.root_tmp / "real.json"
        self.manifest_path.rename(real)
        self.manifest_path.symlink_to(real)
        with self.assertRaises(ValueError):
            self.run_build()

    def test_tampered_reviewed_fields_rejected(self):
        changed = self.root_tmp / "tampered.json"
        data = json.loads(self.reviewed.read_text())
        data["reviewed_candidates"][0]["reviewed_value"] = "9999"
        changed.write_text(json.dumps(data))
        self.manifest["source_reviewed_fields_sha256"] = hashlib.sha256(changed.read_bytes()).hexdigest()
        self.invalid(reviewed=changed)

    def test_wrong_recording_rejected(self):
        wrong = self.root_tmp / "wrong.mp4"
        wrong.write_bytes(b"wrong")
        self.invalid(video=wrong)

    def test_edited_source_crop_rejected(self):
        copy = self.root_tmp / "bundle"
        shutil.copytree(self.bundle, copy)
        (copy / "tables/table_01_sample_00.png").write_bytes(b"tampered")
        self.invalid(bundle=copy)

    def test_rejected_observation_not_allowed(self):
        new_decisions = self.root_tmp / "decisions.json"
        edits = json.loads(self.decisions.read_text())
        edits["decisions"][0].update(decision="reject", reviewed_text=None,
                                       visual_evidence_checked=False)
        new_decisions.write_text(json.dumps(edits))
        new_reviewed = self.root_tmp / "reviewed.json"
        review(self.bundle, self.ocr, new_decisions, new_reviewed, recording_path=self.video)
        self.manifest["source_reviewed_fields_sha256"] = hashlib.sha256(new_reviewed.read_bytes()).hexdigest()
        self.invalid(decisions=new_decisions, reviewed=new_reviewed)

    def test_duplicate_json_keys_rejected(self):
        self.manifest_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.run_build()

    def test_output_inside_bundle_rejected(self):
        with self.assertRaises(ValueError):
            build(self.bundle, self.ocr, self.decisions, self.reviewed,
                  self.manifest_path, self.bundle / "no.json", recording_path=self.video)


if __name__ == "__main__":
    unittest.main()
