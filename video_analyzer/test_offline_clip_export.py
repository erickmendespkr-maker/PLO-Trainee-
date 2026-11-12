import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_clip_export import export_clip, sha256_file

class ClipExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=20", "-t", "3", "-c:v", "mpeg4", str(self.source)], check=True)
        self.plan = dict(source_sha256=sha256_file(self.source), table_id=1, hand_id="synthetic-1", start_seconds=.5, end_seconds=2.5, duration_seconds=2., output_name="clip.mp4", review_status="insufficient_data", strategic_verdict_allowed=False)

    def test_exports_mp4_and_sidecar(self):
        result = export_clip(self.source, self.root / "out", self.plan)
        self.assertEqual(result["annotation"], "INSUFFICIENT_DATA")
        self.assertFalse(result["strategic_verdict_allowed"])
        self.assertEqual(result["clip_sha256"], sha256_file(self.root / "out" / "clip.mp4"))
        self.assertEqual(result, json.loads((self.root / "out" / "clip.mp4.json").read_text()))
        self.assertAlmostEqual(result["actual_clip_duration_seconds"], 2., delta=.25)

    def test_modified_source_rejected(self):
        self.plan["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "mismatch"):
            export_clip(self.source, self.root / "out", self.plan)

    def test_path_traversal_rejected(self):
        self.plan["output_name"] = "../bad.mp4"
        with self.assertRaisesRegex(ValueError, "unsafe"):
            export_clip(self.source, self.root / "out", self.plan)

    def test_overrun_rejected(self):
        self.plan.update(end_seconds=5, duration_seconds=4.5)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            export_clip(self.source, self.root / "out", self.plan)

    def test_strategic_verdict_rejected(self):
        self.plan["strategic_verdict_allowed"] = True
        with self.assertRaisesRegex(ValueError, "forbid"):
            export_clip(self.source, self.root / "out", self.plan)

    def test_no_overwrite(self):
        export_clip(self.source, self.root / "out", self.plan)
        with self.assertRaises(FileExistsError):
            export_clip(self.source, self.root / "out", self.plan)

    def test_nan_rejected(self):
        self.plan["start_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid clip"):
            export_clip(self.source, self.root / "out", self.plan)

if __name__ == "__main__":
    unittest.main()
