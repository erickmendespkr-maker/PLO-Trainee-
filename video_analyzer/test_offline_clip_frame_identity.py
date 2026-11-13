"""FFmpeg-backed synthetic checks of exact decoded frame identity."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_clip_frame_identity import audit_exact_frames


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class FrameIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.mkv"
        self.clip = Path(self.tmp.name) / "clip.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=64x48:rate=5:duration=3",
                        "-c:v", "ffv1", "-y", str(self.source)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.source),
                        "-vf", "select=between(n\\,5\\,9),setpts=PTS-STARTPTS",
                        "-vsync", "0", "-c:v", "ffv1", "-y", str(self.clip)], check=True)

    def test_matching_frames(self):
        result = audit_exact_frames(self.source, self.clip, source_first_frame=5)
        self.assertEqual(result["status"], "EXACT_DECODED_FRAMES_MATCH")
        self.assertEqual(result["clip_frames"], 5)
        self.assertFalse(result["approved_for_publication"])

    def test_wrong_interval_detected(self):
        result = audit_exact_frames(self.source, self.clip, source_first_frame=4)
        self.assertEqual(result["status"], "FRAME_CONTENT_MISMATCH")
        self.assertGreater(result["mismatch_count"], 0)

    def test_bad_index(self):
        with self.assertRaises(ValueError):
            audit_exact_frames(self.source, self.clip, source_first_frame=True)

    def test_bad_limit(self):
        with self.assertRaises(ValueError):
            audit_exact_frames(self.source, self.clip, source_first_frame=0, max_frames=301)

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            audit_exact_frames("/missing/file.mp4", self.clip, source_first_frame=0)

    def test_source_short(self):
        with self.assertRaises(ValueError):
            audit_exact_frames(self.source, self.clip, source_first_frame=14)


if __name__ == "__main__":
    unittest.main()
