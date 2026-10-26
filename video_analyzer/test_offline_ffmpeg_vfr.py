"""Synthetic variable-frame-rate timestamp and last-frame extraction regression."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_ffmpeg_frame_provenance import create
from offline_action_evidence_link import link


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class VariableFrameRateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "vfr.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x120:rate=10:duration=1",
                        "-vf", "setpts='if(lt(N,5),N,2*N-5)/(10*TB)'",
                        "-fps_mode", "vfr", "-c:v", "mpeg4", "-q:v", "2",
                        str(self.video)], check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "frame=best_effort_timestamp_time",
                                "-of", "json", str(self.video)], capture_output=True, check=True)
        self.pts = [float(x["best_effort_timestamp_time"]) for x in json.loads(probe.stdout)["frames"]]
        self.assertGreaterEqual(len(self.pts), 8)

    def extract_index(self, frame_index):
        ledger = {"schema_version": 1,
                  "status": "conditional_observation_ledger_not_video_verified",
                  "video_evidence_verified": False, "ready_for_equity_or_ev": False,
                  "variant": "PLO6", "table_id": 4, "hand_label": "vfr-synthetic",
                  "input_canonical_sha256": "b" * 64,
                  "events": [{"event_index": 0, "street": "flop", "actor": "hero", "kind": "check",
                              "source_pts_seconds": self.pts[frame_index], "confidence": 0.2}]}
        ledger_path = self.root / "ledger.json"
        ledger_path.write_text(json.dumps(ledger))
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps({"schema_version": 1, "frames": [{
            "event_index": 0, "frame_index": frame_index,
            "bbox_pixels": [0, 0, 80, 60]}]}))
        out = self.root / "out"
        manifest = create(self.video, ledger_path, request_path, out)
        self.assertAlmostEqual(manifest["observations"][0]["frame_pts_seconds"],
                               self.pts[frame_index], places=4)
        self.assertEqual(link(ledger, manifest, out)["linked_count"], 1)
        self.assertFalse(link(ledger, manifest, out)["ready_for_equity_or_ev"])

    def test_vfr_pts_not_derived_from_nominal_fps(self):
        self.assertGreater(self.pts[6], 0.6)
        self.extract_index(6)

    def test_last_decoded_frame_can_be_extracted(self):
        self.extract_index(len(self.pts) - 1)


if __name__ == "__main__":
    unittest.main()
