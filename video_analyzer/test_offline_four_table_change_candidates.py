"""Synthetic tests: sparse visual differences are never verified hand boundaries."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from offline_four_table_sample_review import build
from offline_four_table_change_candidates import compute, write_report, _feature


class ChangeCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "session.mp4"
        # Entire top-left quadrant changes at t=1, other three stay constant.
        vf = ("drawbox=x=0:y=0:w=160:h=120:color=red:t=fill,"
              "drawbox=x=160:y=0:w=160:h=120:color=green:t=fill,"
              "drawbox=x=0:y=120:w=160:h=120:color=blue:t=fill,"
              "drawbox=x=160:y=120:w=160:h=120:color=yellow:t=fill,"
              "drawbox=x=0:y=0:w=160:h=120:color=white:t=fill:enable='gte(t,1)'")
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=black:s=320x240:r=5:d=3",
                        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-y", str(self.video)], check=True, capture_output=True, timeout=30)
        self.layout = self.root / "layout.json"
        self.layout.write_text(json.dumps({"schema_version": 1, "layout": "grid",
                                           "rows": 2, "columns": 2}))
        self.bundle = self.root / "bundle"
        build(self.video, self.layout, self.bundle, [0.2, 1.2, 2.2])

    def test_only_changed_quadrant_is_flagged(self):
        report = compute(self.bundle, 0.12)
        self.assertEqual(len(report["tables"]), 4)
        self.assertEqual([len(t["comparisons"]) for t in report["tables"]], [2] * 4)
        flags = [[e["candidate_visual_change"] for e in t["comparisons"]]
                 for t in report["tables"]]
        self.assertEqual(flags, [[True, False], [False, False], [False, False], [False, False]])
        self.assertGreater(report["tables"][0]["comparisons"][0]["mean_absolute_difference"], 0.12)

    def test_never_confuses_change_with_hand_fact(self):
        r = compute(self.bundle)
        for field in ("hand_boundaries_verified", "cards_actions_verified",
                      "ready_for_equity_or_ev", "automatic_clip_selection_authorized"):
            self.assertIs(r[field], False)
        self.assertIn("not_a_verified_hand_boundary", r["tables"][0]["comparisons"][0]["interpretation"])

    def test_report_create_only_and_deterministic(self):
        out = self.root / "report.json"
        report = write_report(self.bundle, out)
        self.assertEqual(json.loads(out.read_text()), report)
        self.assertEqual(compute(self.bundle), report)
        with self.assertRaisesRegex(ValueError, "existing"):
            write_report(self.bundle, out)
        self.assertEqual(json.loads(out.read_text()), report)

    def test_reject_tampered_crop(self):
        crop = self.bundle / "tables/table_01_sample_00.png"
        crop.write_bytes(crop.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "hash"):
            compute(self.bundle)

    def test_reject_modified_manifest(self):
        p = self.bundle / "region_samples.json"
        doc = json.loads(p.read_text())
        doc["ready_for_equity_or_ev"] = True
        p.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "Unsafe bundle"):
            compute(self.bundle)

    def test_reject_invalid_thresholds(self):
        for value in (0, -1, 1.1, float("nan"), float("inf"), True, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute(self.bundle, value)

    def test_no_partial_output_if_decoder_fails(self):
        out = self.root / "report.json"
        with mock.patch("offline_four_table_change_candidates._feature", side_effect=ValueError("decode")):
            with self.assertRaisesRegex(ValueError, "decode"):
                write_report(self.bundle, out)
        self.assertFalse(out.exists())

    def test_reject_symlink_report_destination(self):
        target = self.root / "target.json"
        target.write_text("sentinel")
        out = self.root / "report.json"
        out.symlink_to(target)
        with self.assertRaises(ValueError):
            write_report(self.bundle, out)
        self.assertEqual(target.read_text(), "sentinel")

    def test_decoded_feature_has_256_bytes(self):
        crop = self.bundle / "tables/table_01_sample_00.png"
        self.assertEqual(len(_feature(crop)), 256)


if __name__ == "__main__":
    unittest.main()
