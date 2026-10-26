"""Synthetic batch extraction tests, independent of real user footage."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import offline_ffmpeg_batch_frame_provenance as batch
from offline_ffmpeg_frame_provenance import create as legacy_create
from offline_action_evidence_link import link


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-q:v", "2", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root_case = Path(tmp.name)
        self.ledger = {
            "schema_version": 1, "status": "conditional_observation_ledger_not_video_verified",
            "video_evidence_verified": False, "ready_for_equity_or_ev": False,
            "variant": "PLO6", "table_id": 4, "hand_label": "batch-synthetic",
            "input_canonical_sha256": "b" * 64,
            "events": [{"event_index": i, "street": "flop", "actor": "hero", "kind": "call",
                        "source_pts_seconds": i / 10, "confidence": 0.4} for i in range(5)],
        }
        self.req = {"schema_version": 1, "frames": [
            {"event_index": 1, "frame_index": 1, "bbox_pixels": [10, 10, 80, 60]},
            {"event_index": 2, "frame_index": 2, "bbox_pixels": [0, 0, 160, 120]},
        ]}
        self.ledger_path = self.root_case / "ledger.json"
        self.req_path = self.root_case / "req.json"
        self.out = self.root_case / "out"

    def write(self):
        self.ledger_path.write_text(json.dumps(self.ledger))
        self.req_path.write_text(json.dumps(self.req))

    def create(self, video=None):
        self.write()
        return batch.create(video or self.video, self.ledger_path, self.req_path, self.out)

    def test_two_frames_and_link(self):
        manifest = self.create()
        self.assertEqual(len(manifest["observations"]), 2)
        self.assertEqual(link(self.ledger, manifest, self.out)["linked_count"], 2)
        self.assertFalse(link(self.ledger, manifest, self.out)["ready_for_equity_or_ev"])
        self.assertEqual([round(x["frame_pts_seconds"], 1) for x in manifest["observations"]], [.1, .2])

    def test_single_video_decode_for_multiple_frames(self):
        real_run = batch.run
        commands = []
        def spy(args, timeout):
            commands.append(args)
            return real_run(args, timeout)
        with patch.object(batch, "run", side_effect=spy):
            self.create()
        video_inputs = [cmd for cmd in commands if "-i" in cmd and
                        cmd[cmd.index("-i") + 1] == str(self.video)]
        self.assertEqual(len(video_inputs), 1)
        self.assertEqual(len(commands), 3)  # one video decode + two PNG crops

    def test_duplicate_frame_reuses_decoding(self):
        self.req["frames"][1]["frame_index"] = 1
        self.req["frames"][1]["bbox_pixels"] = [0, 0, 40, 40]
        manifest = self.create()
        self.assertEqual([x["frame_pts_seconds"] for x in manifest["observations"]], [.1, .1])
        self.assertEqual(json.loads((self.out / "provenance_status.json").read_text())
                         ["distinct_frames_decoded"], 1)

    def test_request_order_preserved_when_frame_indices_unsorted(self):
        self.req["frames"] = list(reversed(self.req["frames"]))
        manifest = self.create()
        self.assertEqual([x["event_index"] for x in manifest["observations"]], [2, 1])
        self.assertEqual([round(x["frame_pts_seconds"], 1) for x in manifest["observations"]], [.2, .1])

    def test_full_png_removed(self):
        self.create()
        self.assertFalse((self.out / "_temporary_full_frames").exists())
        self.assertEqual(len(list(self.out.glob("*.png"))), 2)

    def test_output_matches_legacy_pts_and_dimensions(self):
        self.create()
        legacy_dir = self.root_case / "legacy"
        old = legacy_create(self.video, self.ledger_path, self.req_path, legacy_dir)
        new = json.loads((self.out / "evidence_manifest.json").read_text())
        self.assertEqual([x["frame_pts_seconds"] for x in new["observations"]],
                         [x["frame_pts_seconds"] for x in old["observations"]])
        for row in new["observations"]:
            raw = (self.out / row["crop_path"]).read_bytes()
            self.assertEqual((int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")),
                             tuple(row["bbox_pixels"][2:]))

    def test_recording_hash_verified(self):
        manifest = self.create()
        self.assertEqual(manifest["source_recording_sha256"], hashlib.sha256(self.video.read_bytes()).hexdigest())
        status = json.loads((self.out / "provenance_status.json").read_text())
        self.assertTrue(status["source_sha256_verified_before_and_after"])
        self.assertFalse(status["ocr_verified"])
        self.assertFalse(status["equity_ev_authorized"])

    def test_last_frame(self):
        self.req["frames"] = [{"event_index": 4, "frame_index": 19,
                               "bbox_pixels": [0, 0, 160, 120]}]
        self.ledger["events"][4]["source_pts_seconds"] = 1.9
        manifest = self.create()
        self.assertAlmostEqual(manifest["observations"][0]["frame_pts_seconds"], 1.9)

    def test_missing_frame_cleans_output(self):
        self.req["frames"][0]["frame_index"] = 200
        with self.assertRaisesRegex(ValueError, "Missing/extra selected frame PTS"):
            self.create()
        self.assertFalse(self.out.exists())

    def test_wrong_event_pts_cleans_output(self):
        self.req["frames"][0]["frame_index"] = 19
        with self.assertRaisesRegex(ValueError, "PTS too far"):
            self.create()
        self.assertFalse(self.out.exists())

    def test_invalid_bbox(self):
        self.req["frames"][0]["bbox_pixels"] = [150, 100, 30, 30]
        with self.assertRaisesRegex(ValueError, "Crop outside"):
            self.create()
        self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        self.create()
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            self.create()

    def test_invalid_frame_index(self):
        self.req["frames"][0]["frame_index"] = True
        with self.assertRaisesRegex(ValueError, "Invalid frame index"):
            self.create()
        self.assertFalse(self.out.exists())

    def test_source_tamper_detected(self):
        real_hash = batch.source_hash
        counter = [0]
        def hash_mock(path):
            counter[0] += 1
            return real_hash(path) if counter[0] == 1 else "f" * 64
        with patch.object(batch, "source_hash", side_effect=hash_mock):
            with self.assertRaisesRegex(ValueError, "Recording changed"):
                self.create()
        self.assertFalse(self.out.exists())

    def test_missing_ledger(self):
        self.write()
        self.ledger_path.unlink()
        with self.assertRaises(ValueError):
            batch.create(self.video, self.ledger_path, self.req_path, self.out)
        self.assertFalse(self.out.exists())

    def test_no_symlink_source(self):
        alias = self.root_case / "alias.mp4"
        alias.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, "Unsafe recording"):
            self.create(alias)
        self.assertFalse(self.out.exists())

    def test_crop_tamper_detected_by_link(self):
        manifest = self.create()
        (self.out / "event_001.png").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            link(self.ledger, manifest, self.out)

    def test_four_table_id_is_preserved(self):
        manifest = self.create()
        self.assertEqual(manifest["table_id"], 4)

    def test_vfr_timestamp(self):
        video = self.root_case / "vfr.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=1",
                        "-vf", "setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
                        "-fps_mode", "vfr", "-c:v", "mpeg4", "-q:v", "2", str(video)], check=True)
        self.req["frames"] = [{"event_index": 4, "frame_index": 6,
                               "bbox_pixels": [0, 0, 80, 60]}]
        self.ledger["events"][4]["source_pts_seconds"] = 0.7
        manifest = self.create(video)
        self.assertAlmostEqual(manifest["observations"][0]["frame_pts_seconds"], 0.7, places=4)


if __name__ == "__main__":
    unittest.main()