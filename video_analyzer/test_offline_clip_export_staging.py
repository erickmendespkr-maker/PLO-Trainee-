"""Regression for isolated MP4 staging in offline export (no live poker)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import offline_clip_export as module
except ImportError:
    import offline_clip_export as module


class ClipStagingTests(unittest.TestCase):
    def test_two_exports_use_distinct_private_partial_paths(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.mp4"
            source.write_bytes(b"synthetic")
            output = Path(root) / "out"
            plan = {
                "source_sha256": "a" * 64,
                "output_name": "clip.mp4",
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "duration_seconds": 1.0,
                "review_status": "insufficient_data",
                "strategic_verdict_allowed": False,
            }
            observed = []
            def fake_run(command, **kwargs):
                partial = Path(command[-1])
                observed.append(partial)
                partial.write_bytes(b"synthetic mp4")
            def fake_publish(video, json_file, target, sidecar):
                # Deliberately do not publish: allow another export with same name.
                self.assertTrue(video.is_file())
                self.assertTrue(json_file.is_file())
            with patch.object(module, "validate_clip_plan"), \
                 patch.object(module, "sha256_file", return_value="a" * 64), \
                 patch.object(module, "probe_duration", side_effect=lambda p: 10 if Path(p) == source else 1), \
                 patch.object(module.subprocess, "run", side_effect=fake_run), \
                 patch.object(module, "publish_pair_no_clobber", side_effect=fake_publish):
                module.export_clip(source, output, plan)
                module.export_clip(source, output, plan)
            self.assertEqual(len(observed), 2)
            self.assertNotEqual(observed[0], observed[1])
            self.assertTrue(all(not p.exists() for p in observed))
            self.assertFalse(list(output.glob("*.partial.mp4")))


if __name__ == "__main__":
    unittest.main()
