"""Synthetic-only tests of offline terminal-frame sequence diagnostics."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ffmpeg_clip_tail_sequence_audit import (
    FRAME_BYTES, analyze_tail_frames, audit, frame_mae, main,
)


def frame(value):
    return bytes([value]) * FRAME_BYTES


class PureSequenceTests(unittest.TestCase):
    def test_exact_tail(self):
        r = analyze_tail_frames([frame(i * 20) for i in range(8)],
                                [frame(i * 20) for i in range(8)])
        self.assertEqual(r["classification"], "no_anomaly_detected_in_compared_tail")
        self.assertEqual(r["terminal_frame_mae_0_to_255"], 0)

    def test_extra_terminal_duplicate_detected(self):
        r = analyze_tail_frames([frame(i * 20) for i in range(8)],
                                [frame(i * 20) for i in range(8)] + [frame(140)])
        self.assertTrue(r["possible_added_terminal_duplicate"])
        self.assertEqual(r["classification"], "possible_added_terminal_duplicate")

    def test_missing_terminal_frame_detected(self):
        r = analyze_tail_frames([frame(i * 20) for i in range(8)],
                                [frame(i * 20) for i in range(7)])
        self.assertTrue(r["possible_missing_terminal_frames"])
        self.assertEqual(r["closest_source_tail_frame_offset_from_end"], 1)

    def test_static_source_does_not_claim_duplicate(self):
        r = analyze_tail_frames([frame(90)] * 8, [frame(90)] * 9)
        self.assertEqual(r["classification"],
                         "indeterminate_static_or_insufficient_source_motion")
        self.assertFalse(r["possible_added_terminal_duplicate"])

    def test_unrelated_tail_indeterminate(self):
        r = analyze_tail_frames([frame(i * 20) for i in range(8)],
                                [frame(250), frame(240), frame(230)])
        self.assertEqual(r["classification"], "indeterminate_terminal_difference")

    def test_only_one_frame_indeterminate(self):
        r = analyze_tail_frames([frame(50)], [frame(50)])
        self.assertEqual(r["classification"],
                         "indeterminate_static_or_insufficient_source_motion")

    def test_invalid_empty_sequence(self):
        with self.assertRaisesRegex(ValueError, "Empty/oversized"):
            analyze_tail_frames([], [frame(1)])

    def test_invalid_frame_dimensions(self):
        with self.assertRaisesRegex(ValueError, "Invalid decoded"):
            analyze_tail_frames([b"wrong"], [frame(1)])

    def test_mae_exact(self):
        self.assertEqual(frame_mae(frame(0), frame(255)), 255)

    def test_does_not_treat_boolean_as_valid_start(self):
        with self.assertRaisesRegex(ValueError, "Invalid requested start"):
            audit("anything.mp4", "other.mp4", True)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class RealFFmpegSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "source.mp4"
        cls.clip = cls.root / "clip.mp4"
        cls.short = cls.root / "short.mp4"
        cls.padded = cls.root / "padded.mp4"
        cls.static = cls.root / "static.mp4"
        cls.static_clip = cls.root / "static_clip.mp4"
        cls.remux = cls.root / "remux.mp4"
        cls.vfr = cls.root / "vfr.mp4"
        def ff(*args):
            subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                            *map(str, args)], check=True, timeout=90)
        ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=3",
           "-an", "-c:v", "mpeg4", "-q:v", "2", cls.source)
        ff("-ss", "1", "-i", cls.source, "-t", "2", "-an", "-c:v", "mpeg4",
           "-q:v", "2", cls.clip)
        ff("-ss", "1", "-i", cls.source, "-t", "1.7", "-an", "-c:v", "mpeg4",
           "-q:v", "2", cls.short)
        ff("-i", cls.clip, "-vf", "tpad=stop_mode=clone:stop_duration=0.3",
           "-an", "-c:v", "mpeg4", "-q:v", "2", cls.padded)
        ff("-f", "lavfi", "-i", "color=c=red:s=160x120:r=10:d=3",
           "-an", "-c:v", "mpeg4", "-q:v", "2", cls.static)
        ff("-ss", "1", "-i", cls.static, "-t", "2", "-an", "-c:v", "mpeg4",
           "-q:v", "2", cls.static_clip)
        ff("-i", cls.source, "-c", "copy", "-movflags", "+faststart", cls.remux)
        ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=3",
           "-vf", "setpts='if(lt(N,15),N,2*N-15)/(10*TB)'",
           "-fps_mode", "vfr", "-an", "-c:v", "mpeg4", "-q:v", "2", cls.vfr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_full_clip_no_anomaly(self):
        r = audit(self.source, self.clip, 1)
        self.assertEqual(r["classification"], "no_anomaly_detected_in_compared_tail")
        self.assertFalse(r["visual_provenance_verified"])
        self.assertFalse(r["equity_ev_authorized"])

    def test_truncated_clip_flags_possible_missing(self):
        r = audit(self.source, self.short, 1)
        self.assertTrue(r["possible_missing_terminal_frames"], r)

    def test_padding_flags_possible_duplicate(self):
        r = audit(self.source, self.padded, 1)
        self.assertTrue(r["possible_added_terminal_duplicate"], r)

    def test_static_source_stays_indeterminate(self):
        r = audit(self.static, self.static_clip, 1)
        self.assertFalse(r["possible_added_terminal_duplicate"])
        self.assertEqual(r["classification"],
                         "indeterminate_static_or_insufficient_source_motion")

    def test_remux_same_frames_no_anomaly(self):
        r = audit(self.source, self.remux, 0)
        self.assertEqual(r["classification"], "no_anomaly_detected_in_compared_tail")

    def test_vfr_no_claims(self):
        r = audit(self.vfr, self.clip, 1)
        self.assertFalse(r["visual_provenance_verified"])
        self.assertIsInstance(r["classification"], str)

    def test_cli_no_overwrite(self):
        target = self.root / "report.json"
        self.assertEqual(main([str(self.source), str(self.clip), "1", str(target)]), 0)
        self.assertEqual(json.loads(target.read_text())["schema_version"], 1)
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            main([str(self.source), str(self.clip), "1", str(target)])

    def test_symlink_rejected(self):
        link = self.root / "symlink.mp4"
        link.symlink_to(self.clip)
        with self.assertRaisesRegex(ValueError, "Unsafe video path"):
            audit(self.source, link, 1)

    def test_same_file_rejected(self):
        with self.assertRaisesRegex(ValueError, "identical"):
            audit(self.source, self.source, 0)

    def test_missing_file_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe video path"):
            audit(self.root / "missing.mp4", self.clip, 1)

    def test_start_beyond_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "Start beyond"):
            audit(self.source, self.clip, 3)

    def test_changed_source_hash_rejected(self):
        from offline_ffmpeg_clip_tail_sequence_audit import _hash_regular as original
        counter = {"n": 0}
        def fake(path):
            counter["n"] += 1
            return "0" * 64 if counter["n"] > 2 else original(path)
        with patch("offline_ffmpeg_clip_tail_sequence_audit._hash_regular", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "Video changed"):
                audit(self.source, self.clip, 1)


if __name__ == "__main__":
    unittest.main()