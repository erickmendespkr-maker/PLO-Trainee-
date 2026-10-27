"""Synthetic regression and real FFmpeg/Tesseract integration tests for OCR proposals."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_four_table_ocr_proposals as m
from offline_four_table_sample_review import build


class FourTableOCRProposalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("ffmpeg", "ffprobe", "tesseract"):
            if not shutil.which(tool):
                raise RuntimeError(f"Required integration test tool missing: {tool}")
        cls.base = tempfile.TemporaryDirectory()
        cls.root = Path(cls.base.name)
        cls.video = cls.root / "synthetic.mp4"
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not Path(font).is_file():
            raise RuntimeError("Test font unavailable")
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=white:s=640x360:r=3:d=2",
                        "-vf", f"drawtext=fontfile={font}:text='POT 120':fontcolor=black:fontsize=40:x=16:y=32",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        layout = cls.root / "layout.json"
        layout.write_text(json.dumps({"schema_version": 1, "layout": "grid",
                                      "rows": 2, "columns": 2}))
        cls.bundle = cls.root / "bundle"
        build(cls.video, layout, cls.bundle, [0.4, 1.2])
        cls.source_sha = hashlib.sha256((cls.bundle / "region_samples.json").read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.manifest_path = self.path / "roi.json"
        self.out = self.path / "ocr.json"
        self.task = {"table_id": 1, "sample_index": 0, "field": "pot",
                     "roi": {"x": 0, "y": 0, "width": 310, "height": 100}}
        self.manifest = {"schema_version": 1, "source_manifest_sha256": self.source_sha,
                         "tasks": [self.task]}
        self.write()

    def write(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def scan(self):
        return m.scan(self.bundle, self.manifest_path, self.out,
                      recording_path=self.video)

    def assert_rejected(self):
        self.write()
        with self.assertRaises((ValueError, FileExistsError)):
            self.scan()
        self.assertFalse(self.out.exists())

    def test_real_tesseract_reads_text_without_promoting_to_fact(self):
        report = self.scan()
        self.assertEqual(report["analysis_status"], m.STATUS)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["automatic_hand_or_action_inference"])
        self.assertTrue(report["requires_manual_review"])
        self.assertFalse(report["engine_confidence_is_calibrated_probability"])
        candidate = report["candidates"][0]
        self.assertEqual(candidate["raw_ocr_text"], "POT 120")
        self.assertEqual(candidate["status"], "needs_manual_review")
        self.assertIsNone(candidate["parsed_candidate"])
        self.assertGreater(candidate["tesseract_mean_word_confidence_uncalibrated"], 0.7)
        self.assertEqual(candidate["source_crop_sha256"],
                         json.loads((self.bundle / "region_samples.json").read_text())
                         ["samples"][0]["table_crops"][0]["sha256"])
        self.assertEqual(json.loads(self.out.read_text()), report)

    def test_second_table_and_sample_preserve_source_pts(self):
        self.manifest["tasks"] = [{"table_id": 2, "sample_index": 1,
                                   "field": "action", "roi": {"x": 1, "y": 1,
                                                                "width": 100, "height": 80}}]
        self.write()
        report = self.scan()
        self.assertEqual(report["candidates"][0]["decoded_source_pts_seconds"],
                         json.loads((self.bundle / "region_samples.json").read_text())
                         ["samples"][1]["decoded_source_pts_seconds"])
        self.assertEqual(report["candidates"][0]["field"], "action")

    def test_all_six_fields_allowed_but_unverified(self):
        self.manifest["tasks"] = [dict(self.task, field=f) for f in sorted(m.FIELDS)]
        self.write()
        report = self.scan()
        self.assertEqual(len(report["candidates"]), 6)
        self.assertTrue(all(x["status"] == "needs_manual_review" for x in report["candidates"]))

    def test_duplicate_task_rejected(self):
        self.manifest["tasks"].append(self.task.copy())
        self.assert_rejected()

    def test_unbound_manifest_rejected(self):
        self.manifest["source_manifest_sha256"] = "0" * 64
        self.assert_rejected()

    def test_boolean_table_id_rejected(self):
        self.task["table_id"] = True
        self.assert_rejected()

    def test_negative_sample_index_rejected(self):
        self.task["sample_index"] = -1
        self.assert_rejected()

    def test_unknown_field_rejected(self):
        self.task["field"] = "opponent_hidden_cards"
        self.assert_rejected()

    def test_roi_outside_crop_rejected(self):
        self.task["roi"]["x"] = 300
        self.assert_rejected()

    def test_too_small_roi_rejected(self):
        self.task["roi"]["width"] = 1
        self.assert_rejected()

    def test_boolean_roi_rejected(self):
        self.task["roi"]["width"] = True
        self.assert_rejected()

    def test_empty_tasks_rejected(self):
        self.manifest["tasks"] = []
        self.assert_rejected()

    def test_too_many_tasks_rejected(self):
        self.manifest["tasks"] = [dict(self.task, sample_index=i) for i in range(33)]
        self.assert_rejected()

    def test_extra_task_fields_rejected(self):
        self.task["approve_math"] = True
        self.assert_rejected()

    def test_duplicate_json_key_rejected(self):
        self.manifest_path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.scan()

    def test_existing_output_never_overwritten(self):
        self.out.write_text("original")
        with self.assertRaises(ValueError):
            self.scan()
        self.assertEqual(self.out.read_text(), "original")

    def test_symlink_manifest_rejected(self):
        target = self.path / "actual.json"
        self.manifest_path.rename(target)
        self.manifest_path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.scan()

    def test_modified_source_crop_rejected(self):
        copy = self.path / "tampered"
        shutil.copytree(self.bundle, copy)
        (copy / "tables/table_01_sample_00.png").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            m.scan(copy, self.manifest_path, self.out)
        self.assertFalse(self.out.exists())

    def test_source_video_hash_mismatch_rejected(self):
        fake = self.path / "fake.mp4"
        fake.write_bytes(b"not the source")
        with self.assertRaises(ValueError):
            m.scan(self.bundle, self.manifest_path, self.out, recording_path=fake)

    def test_tesseract_failure_no_partial_output(self):
        with mock.patch.object(m.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(ValueError):
                self.scan()
        self.assertFalse(self.out.exists())

    def test_parse_tsv_empty_and_bad(self):
        self.assertEqual(m._parse_tsv(b"text\tconf\n\t-1\n"), ("", 0, None))
        with self.assertRaises(ValueError):
            m._parse_tsv(b"bad\ntext\n")
        with self.assertRaises(ValueError):
            m._parse_tsv(b"text\tconf\nPOT\tnan\n")
        with self.assertRaises(ValueError):
            m._parse_tsv(b"text\tconf\nPOT\t120\n")

    def test_crop_changed_during_ocr_rejected_without_output(self):
        copy = self.path / "changing"
        shutil.copytree(self.bundle, copy)
        crop = copy / "tables/table_01_sample_00.png"
        def modify(*args):
            crop.write_bytes(b"tampered while reading")
            return "POT 120", 2, 0.95
        with mock.patch.object(m, "_ocr", side_effect=modify):
            with self.assertRaises(ValueError):
                m.scan(copy, self.manifest_path, self.out)
        self.assertFalse(self.out.exists())

    def test_manifest_changed_during_ocr_rejected_without_output(self):
        copy = self.path / "changing"
        shutil.copytree(self.bundle, copy)
        source_manifest = copy / "region_samples.json"
        def modify(*args):
            source_manifest.write_text(source_manifest.read_text() + " ")
            return "POT 120", 2, 0.95
        with mock.patch.object(m, "_ocr", side_effect=modify):
            with self.assertRaises(ValueError):
                m.scan(copy, self.manifest_path, self.out)
        self.assertFalse(self.out.exists())

    def test_output_cannot_be_inside_verified_bundle(self):
        with self.assertRaises(ValueError):
            m.scan(self.bundle, self.manifest_path, self.bundle / "unwanted.json")


if __name__ == "__main__":
    unittest.main()
