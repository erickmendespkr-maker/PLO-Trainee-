"""Offline synthetic video tests; no live poker or user footage."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_ffmpeg_frame_provenance import create, read_request, source_hash, probe
from offline_action_evidence_link import link


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class FrameProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=2", "-an",
                        "-c:v", "mpeg4", "-q:v", "2", str(cls.video)], check=True)
        cls.ledger = {
            "schema_version": 1, "status": "conditional_observation_ledger_not_video_verified",
            "video_evidence_verified": False, "ready_for_equity_or_ev": False,
            "variant": "PLO5", "table_id": 1, "hand_label": "synthetic-hand",
            "input_canonical_sha256": "a" * 64,
            "events": [{"event_index": i, "street": "preflop", "actor": "A", "kind": "call",
                        "source_pts_seconds": i / 10, "confidence": 0.4} for i in range(3)],
        }
        cls.ledger_path = cls.root / "ledger.json"
        cls.ledger_path.write_text(json.dumps(cls.ledger))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_case.cleanup)
        self.work = Path(self.tmp_case.name)
        self.req = {"schema_version": 1, "frames": [{"event_index": 1,
                    "frame_index": 1, "bbox_pixels": [10, 10, 80, 60]}]}
        self.req_path = self.work / "request.json"
        self.out = self.work / "result"

    def write_req(self):
        self.req_path.write_text(json.dumps(self.req))

    def generate(self):
        self.write_req()
        return create(self.video, self.ledger_path, self.req_path, self.out)

    def test_extract_and_link_with_verified_source_bytes(self):
        manifest = self.generate()
        self.assertEqual(manifest["source_recording_sha256"], hashlib.sha256(self.video.read_bytes()).hexdigest())
        self.assertAlmostEqual(manifest["observations"][0]["frame_pts_seconds"], 0.1, places=4)
        self.assertEqual(manifest["observations"][0]["recognition_confidence"], 0.0)
        self.assertEqual(manifest["observations"][0]["extraction_method"], "ffmpeg_frame")
        report = link(self.ledger, manifest, self.out)
        self.assertEqual(report["linked_count"], 1)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["video_evidence_verified"])
        self.assertTrue(json.loads((self.out / "provenance_status.json").read_text())["source_sha256_verified_before_and_after"])

    def test_two_distinct_frames(self):
        self.req["frames"].append({"event_index": 2, "frame_index": 2,
                                   "bbox_pixels": [0, 0, 160, 120]})
        manifest = self.generate()
        self.assertEqual(len(manifest["observations"]), 2)
        self.assertEqual([round(x["frame_pts_seconds"], 1) for x in manifest["observations"]], [0.1, 0.2])
        self.assertNotEqual(manifest["observations"][0]["crop_sha256"],
                            manifest["observations"][1]["crop_sha256"])

    def test_crop_png_dimensions(self):
        self.generate()
        raw = (self.out / "event_001.png").read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")), (80, 60))

    def test_unsupported_frame_index_removes_output(self):
        self.req["frames"][0]["frame_index"] = 50
        self.write_req()
        with self.assertRaises(ValueError):
            create(self.video, self.ledger_path, self.req_path, self.out)
        self.assertFalse(self.out.exists())

    def test_wrong_pts_removes_output(self):
        self.req["frames"][0]["frame_index"] = 19
        self.write_req()
        with self.assertRaisesRegex(ValueError, "PTS too far"):
            create(self.video, self.ledger_path, self.req_path, self.out)
        self.assertFalse(self.out.exists())

    def test_outside_crop_rejected(self):
        self.req["frames"][0]["bbox_pixels"] = [100, 100, 80, 60]
        self.write_req()
        with self.assertRaisesRegex(ValueError, "outside video"):
            create(self.video, self.ledger_path, self.req_path, self.out)
        self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        self.generate()
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            create(self.video, self.ledger_path, self.req_path, self.out)

    def test_duplicate_event_request(self):
        self.req["frames"].append(copy.deepcopy(self.req["frames"][0]))
        self.write_req()
        with self.assertRaisesRegex(ValueError, "event index"):
            read_request(self.req_path)

    def test_bool_frame_index_rejected(self):
        self.req["frames"][0]["frame_index"] = True
        self.write_req()
        with self.assertRaisesRegex(ValueError, "frame index"):
            read_request(self.req_path)

    def test_invalid_bbox_rejected(self):
        self.req["frames"][0]["bbox_pixels"] = [0, 0, 0, 10]
        self.write_req()
        with self.assertRaisesRegex(ValueError, "bounding box"):
            read_request(self.req_path)

    def test_duplicate_json_key_rejected(self):
        self.req_path.write_text('{"schema_version":1,"schema_version":1,"frames":[]}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            read_request(self.req_path)

    def test_symlink_video_rejected(self):
        linked = self.work / "linked.mp4"
        linked.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, "Unsafe recording"):
            source_hash(linked)

    def test_source_tamper_detected_by_second_hash(self):
        self.write_req()
        original = source_hash
        calls = [0]
        def spoof(path):
            calls[0] += 1
            return original(path) if calls[0] == 1 else "f" * 64
        with patch("offline_ffmpeg_frame_provenance.source_hash", side_effect=spoof):
            with self.assertRaisesRegex(ValueError, "Recording changed"):
                create(self.video, self.ledger_path, self.req_path, self.out)
        self.assertFalse(self.out.exists())

    def test_probe_video(self):
        w, h, duration = probe(self.video)
        self.assertEqual((w, h), (160, 120))
        self.assertAlmostEqual(duration, 2.0)

    def test_manifest_sha_immutable_after_crop_tamper(self):
        manifest = self.generate()
        (self.out / "event_001.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            link(self.ledger, manifest, self.out)

    def test_event_out_of_ledger(self):
        self.req["frames"][0]["event_index"] = 4
        self.write_req()
        with self.assertRaisesRegex(ValueError, "outside ledger"):
            create(self.video, self.ledger_path, self.req_path, self.out)

    def test_missing_video_rejected(self):
        self.write_req()
        with self.assertRaises(ValueError):
            create(self.work / "missing.mp4", self.ledger_path, self.req_path, self.out)


if __name__ == "__main__":
    unittest.main()
