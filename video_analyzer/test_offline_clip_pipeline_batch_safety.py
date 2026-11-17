"""Regression checks for candidate clip batch preflight and rollback."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_clip_pipeline import render_candidates


class BatchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "input.mp4"
        self.source.write_bytes(b"synthetic placeholder; ffprobe mocked")
        self.out = self.root / "out"
        self.proposals = [{"table_id": 1, "start_seconds": 1, "end_seconds": 2,
                           "evidence_sha256": "a" * 64}]

    def test_existing_report_prevents_render(self):
        self.out.mkdir()
        (self.out / "candidate_clip_report.json").write_text("existing")
        with patch("offline_clip_pipeline.probe_video", return_value={"format": {"duration": "10"}}), \
             patch("offline_clip_pipeline.subprocess.run") as run:
            with self.assertRaises(FileExistsError):
                render_candidates(self.source, self.out, self.proposals)
            run.assert_not_called()

    def test_existing_clip_prevents_render(self):
        self.out.mkdir()
        with patch("offline_clip_pipeline.probe_video", return_value={"format": {"duration": "10"}}), \
             patch("offline_clip_pipeline.build_clip_manifest", return_value={
                 "clips": [{"clip_id": "candidate"}]}), \
             patch("offline_clip_pipeline.subprocess.run") as run:
            (self.out / "candidate.mp4").write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                render_candidates(self.source, self.out, self.proposals)
            run.assert_not_called()

    def test_second_render_failure_rolls_back_first_clip(self):
        clips = [{"clip_id": "first"}, {"clip_id": "second"}]
        def run(argv, **kwargs):
            destination = Path(argv[-1])
            destination.write_bytes(b"fake render")
            if destination.name == "second.mp4":
                raise RuntimeError("render failed")
        with patch("offline_clip_pipeline.probe_video", return_value={"format": {"duration": "10"}}), \
             patch("offline_clip_pipeline.build_clip_manifest", return_value={"clips": clips}), \
             patch("offline_clip_pipeline.ffmpeg_clip_arguments",
                   side_effect=lambda src, dst, clip: ["ffmpeg", "-y", dst]), \
             patch("offline_clip_pipeline.audit_render", return_value={"ok": True}), \
             patch("offline_clip_pipeline.subprocess.run", side_effect=run):
            with self.assertRaises(RuntimeError):
                render_candidates(self.source, self.out, self.proposals)
        self.assertFalse((self.out / "first.mp4").exists())
        self.assertFalse((self.out / "second.mp4").exists())
        self.assertFalse((self.out / "candidate_clip_report.json").exists())


if __name__ == "__main__":
    unittest.main()
