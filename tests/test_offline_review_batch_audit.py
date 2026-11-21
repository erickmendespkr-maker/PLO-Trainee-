"""Synthetic regression tests for offline review batch audit."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from video_analyzer.offline_review_batch_audit import audit_directory, main

class BatchAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_empty_directory_is_not_success(self):
        self.assertEqual(audit_directory(self.root)["total"], 0)
        self.assertEqual(main([str(self.root)]), 1)

    def test_mixed_clips_and_deterministic_order(self):
        for name in ("b.mp4", "a.mp4"):
            (self.root / name).write_bytes(b"test")
        def fake_audit(path, *, source=None):
            if path.name == "b.mp4":
                raise ValueError("tampered")
            return {"integrity_verified": True, "source_checked": False}
        with patch("video_analyzer.offline_review_batch_audit.audit_review_export", side_effect=fake_audit):
            report = audit_directory(self.root)
        self.assertEqual((report["passed"], report["failed"]), (1, 1))
        self.assertEqual([x["clip"] for x in report["results"]], ["a.mp4", "b.mp4"])
        self.assertEqual(report["results"][1]["error_type"], "ValueError")

    def test_invalid_directory_rejected(self):
        with self.assertRaises(ValueError):
            audit_directory(self.root / "missing")

    def test_symlink_directory_rejected(self):
        link = self.root.parent / (self.root.name + "-link")
        link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaises(ValueError):
            audit_directory(link)

    def test_source_is_forwarded(self):
        (self.root / "a.mp4").write_bytes(b"test")
        with patch("video_analyzer.offline_review_batch_audit.audit_review_export",
                   return_value={"integrity_verified": True, "source_checked": True}) as mock:
            report = audit_directory(self.root, source=self.root / "source.mp4")
        self.assertEqual(report["passed"], 1)
        self.assertEqual(mock.call_args.kwargs["source"], self.root / "source.mp4")

if __name__ == "__main__":
    unittest.main()
