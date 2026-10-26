"""Synthetic regression tests for sparse indexed seeks and PTS verification."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import offline_ffmpeg_batch_frame_provenance as batch
import offline_ffmpeg_seek_frame_provenance as seek


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class IndexedSeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / "source.mp4"
        cls.vfr = cls.root / "vfr.mp4"
        cls.bframes = cls.root / "bframes.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-q:v", "2", str(cls.video)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=1",
                        "-vf", "setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
                        "-fps_mode", "vfr", "-c:v", "mpeg4", "-q:v", "2",
                        str(cls.vfr)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-bf", "2", "-q:v", "2", str(cls.bframes)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_case.cleanup)
        self.case = Path(self.tmp_case.name)
        self.ledger = {"schema_version": 1,
                       "status": "conditional_observation_ledger_not_video_verified",
                       "video_evidence_verified": False, "ready_for_equity_or_ev": False,
                       "variant": "PLO5", "table_id": 2, "hand_label": "synthetic-seek",
                       "input_canonical_sha256": "a" * 64,
                       "events": [{"event_index": i, "street": "flop", "actor": "hero",
                                   "kind": "call", "source_pts_seconds": i / 10,
                                   "confidence": 0.2} for i in range(20)]}
        self.req = {"schema_version": 1, "frames": [
            {"event_index": 1, "frame_index": 1, "bbox_pixels": [0, 0, 80, 60]},
            {"event_index": 19, "frame_index": 19, "bbox_pixels": [20, 20, 60, 40]}]}
        self.ledger_file = self.case / "ledger.json"
        self.req_file = self.case / "requests.json"

    def create(self, video=None, strategy="indexed_seek"):
        self.ledger_file.write_text(json.dumps(self.ledger))
        self.req_file.write_text(json.dumps(self.req))
        return batch.create(video or self.video, self.ledger_file, self.req_file,
                            self.case / strategy, strategy=strategy)

    def test_indexed_matches_full_decode_pts(self):
        new = self.create()
        old = self.create(strategy="full_decode")
        self.assertEqual([x["frame_pts_seconds"] for x in new["observations"]],
                         [x["frame_pts_seconds"] for x in old["observations"]])
        self.assertEqual(new["source_recording_sha256"], old["source_recording_sha256"])
        status = json.loads((self.case / "indexed_seek" / "provenance_status.json").read_text())
        self.assertEqual(status["extraction_strategy"], "indexed_seek")
        self.assertEqual(status["video_decode_passes"], 2)
        self.assertEqual(status["frame_index_probe_passes"], 1)
        self.assertFalse(status["equity_ev_authorized"])

    def test_indexed_last_frame(self):
        self.req["frames"] = [self.req["frames"][-1]]
        result = self.create()
        self.assertAlmostEqual(result["observations"][0]["frame_pts_seconds"], 1.9)

    def test_duplicate_frame_single_seek(self):
        self.req["frames"][1]["frame_index"] = 1
        self.ledger["events"][19]["source_pts_seconds"] = .1
        result = self.create()
        self.assertEqual(len(result["observations"]), 2)
        status = json.loads((self.case / "indexed_seek" / "provenance_status.json").read_text())
        self.assertEqual(status["video_decode_passes"], 1)

    def test_vfr_exact_pts(self):
        self.req["frames"] = [{"event_index": 7, "frame_index": 6,
                               "bbox_pixels": [0, 0, 80, 60]}]
        self.ledger["events"] = self.ledger["events"][:10]
        self.ledger["events"][7]["source_pts_seconds"] = .7
        result = self.create(self.vfr)
        self.assertAlmostEqual(result["observations"][0]["frame_pts_seconds"], .7)

    def test_bframes_index(self):
        self.req["frames"] = [{"event_index": 7, "frame_index": 7,
                               "bbox_pixels": [0, 0, 80, 60]}]
        result = self.create(self.bframes)
        self.assertAlmostEqual(result["observations"][0]["frame_pts_seconds"], .7)

    def test_out_of_range_cleanup(self):
        self.req["frames"][1]["frame_index"] = 200
        with self.assertRaisesRegex(ValueError, "beyond recording"):
            self.create()
        self.assertFalse((self.case / "indexed_seek").exists())

    def test_unknown_strategy(self):
        with self.assertRaisesRegex(ValueError, "Unknown extraction strategy"):
            self.create(strategy="not_supported")

    def test_wrong_pts_rejected(self):
        self.req["frames"] = [self.req["frames"][0]]
        with patch.object(seek, "PTS_RE", __import__("re").compile(r"pts_time:\\s*999")):
            with self.assertRaisesRegex(ValueError, "Missing sought frame PTS"):
                self.create()
        self.assertFalse((self.case / "indexed_seek").exists())

    def test_no_overwrite(self):
        self.create()
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            self.create()


if __name__ == "__main__":
    unittest.main()
