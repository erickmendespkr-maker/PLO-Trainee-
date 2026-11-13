"""Synthetic tests for offline clip evidence manifest (no video or OCR claims)."""
import tempfile
import unittest
from pathlib import Path

from video_analyzer.offline_clip_evidence_manifest import clip_manifest, clip_sha256


class ClipEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clip = Path(self.temp.name) / "synthetic.mp4"
        self.clip.write_bytes(b"synthetic fixture; not actual MP4")
        self.identity = dict(hand_id="h1", table_id=2, video_sha256="a" * 64,
                             start_seconds=10, end_seconds=20)

    def manifest(self, **kwargs):
        params = dict(clip_path=self.clip, identity=self.identity,
                      source_duration=60, clip_start=8, clip_end=22)
        params.update(kwargs)
        return clip_manifest(**params)

    def test_unapproved(self):
        result = self.manifest()
        self.assertFalse(result["approved_for_publication"])
        self.assertEqual(result["clip"]["sha256"], clip_sha256(self.clip))

    def test_valid_binding(self):
        binding = dict(hand_identity={**self.identity, "start_seconds": 10.0, "end_seconds": 20.0},
                       status="IDENTITY_MATCH_ONLY", approved_for_publication=False,
                       report_sha256="b" * 64)
        self.assertEqual(self.manifest(binding=binding)["report_sha256"], "b" * 64)

    def test_reject_wrong_identity(self):
        with self.assertRaises(ValueError):
            self.manifest(binding={"hand_identity": {}})

    def test_reject_clip_not_covering_hand(self):
        with self.assertRaises(ValueError):
            self.manifest(clip_start=12)

    def test_reject_outside_source(self):
        with self.assertRaises(ValueError):
            self.manifest(clip_end=61)

    def test_reject_nan(self):
        with self.assertRaises(ValueError):
            self.manifest(clip_end=float("nan"))

    def test_reject_bool_table(self):
        with self.assertRaises(ValueError):
            self.manifest(identity={**self.identity, "table_id": True})

    def test_reject_symlink(self):
        link = Path(self.temp.name) / "link.mp4"
        link.symlink_to(self.clip)
        with self.assertRaises(ValueError):
            self.manifest(clip_path=link)

    def test_hash_changes_on_modification(self):
        first = self.manifest()["clip"]["sha256"]
        self.clip.write_bytes(b"changed")
        self.assertNotEqual(first, self.manifest()["clip"]["sha256"])

    def test_reject_missing_file(self):
        with self.assertRaises(ValueError):
            self.manifest(clip_path=self.clip.parent / "missing.mp4")


if __name__ == "__main__":
    unittest.main()
