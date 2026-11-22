"""Regression: do not delete a sidecar created by a concurrent exporter."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_analyzer import offline_review_bundle_export as module


class SidecarOwnershipTests(unittest.TestCase):
    def test_concurrent_sidecar_survives_export_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            source.write_bytes(b"synthetic placeholder")
            clip = Path(directory) / "review.mp4"
            sidecar = clip.with_suffix(".json")

            def concurrent_writer(*args, **kwargs):
                sidecar.write_text('{"owner":"other"}', encoding="utf-8")
                raise RuntimeError("simulated competing writer")

            with patch.object(module, "_duration", return_value=10.0), \
                 patch.object(module, "build_clip_report_bundle", return_value={
                     "alignment": {"status": "TEMPORALLY_ALIGNED_ONLY"},
                     "report": {"clip": {}, "status": "INSUFFICIENT_DATA"},
                 }), \
                 patch.object(module, "export_review_clip", side_effect=concurrent_writer):
                with self.assertRaisesRegex(RuntimeError, "competing writer"):
                    module.export_review_bundle(
                        source, clip, {"start_s": 1, "end_s": 2},
                        clip_start_s=1, clip_end_s=2,
                    )
            self.assertEqual(sidecar.read_text(encoding="utf-8"), '{"owner":"other"}')

    def test_existing_sidecar_is_never_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            source.write_bytes(b"synthetic placeholder")
            clip = Path(directory) / "review.mp4"
            sidecar = clip.with_suffix(".json")
            sidecar.write_text("preexisting", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                module.export_review_bundle(source, clip, {}, clip_start_s=1, clip_end_s=2)
            self.assertEqual(sidecar.read_text(encoding="utf-8"), "preexisting")


if __name__ == "__main__":
    unittest.main()
