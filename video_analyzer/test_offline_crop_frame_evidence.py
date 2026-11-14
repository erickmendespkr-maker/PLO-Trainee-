"""Synthetic regression tests for offline crop-frame evidence."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_crop_frame_evidence import collect_crop_frame_evidence

class CropEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.table = {"table_id": 1, "file": "table_1.mkv",
                      "verified_by_human": False, "hand_reconstructed": False}
        self.manifest = {"status": "UNREVIEWED_TABLE_CROPS",
                         "poker_analysis_verified": False, "tables": [self.table]}
        self.write_manifest()
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=64x48:rate=5:duration=2",
                        "-c:v", "ffv1", str(self.directory / "table_1.mkv")], check=True)

    def write_manifest(self):
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest))

    def test_real_ffmpeg_frames(self):
        report = collect_crop_frame_evidence(self.directory, max_samples=3)
        samples = report["tables"][0]["samples"]
        self.assertEqual([s["frame_index"] for s in samples], [0, 4, 9])
        self.assertEqual([s["crop_pts_seconds"] for s in samples], [0.0, 0.8, 1.8])
        self.assertEqual(len({s["rgb_sha256"] for s in samples}), 3)
        self.assertFalse(report["hands_verified"])
        self.assertFalse(report["source_absolute_pts_verified"])

    def test_reproducible(self):
        self.assertEqual(collect_crop_frame_evidence(self.directory),
                         collect_crop_frame_evidence(self.directory))

    def test_rejects_unsupported_verification(self):
        self.manifest["poker_analysis_verified"] = True
        self.write_manifest()
        with self.assertRaises(ValueError):
            collect_crop_frame_evidence(self.directory)

    def test_rejects_hand_claim(self):
        self.table["hand_reconstructed"] = True
        self.write_manifest()
        with self.assertRaises(ValueError):
            collect_crop_frame_evidence(self.directory)

    def test_invalid_sample_limits(self):
        for value in (True, 0, 13, 1.2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                collect_crop_frame_evidence(self.directory, max_samples=value)

    def test_duplicate_id(self):
        self.manifest["tables"].append(dict(self.table))
        self.write_manifest()
        with self.assertRaises(ValueError):
            collect_crop_frame_evidence(self.directory)

    def test_missing_crop(self):
        (self.directory / "table_1.mkv").unlink()
        with self.assertRaises(ValueError):
            collect_crop_frame_evidence(self.directory)

    def test_symlink_crop(self):
        original = self.directory / "table_1.mkv"
        original.rename(self.directory / "original.mkv")
        original.symlink_to(self.directory / "original.mkv")
        with self.assertRaises(ValueError):
            collect_crop_frame_evidence(self.directory)

if __name__ == "__main__":
    unittest.main()
