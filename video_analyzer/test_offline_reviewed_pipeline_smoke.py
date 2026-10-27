"""Offline pipeline smoke tests; stub math is NOT a Monte Carlo validation."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import offline_reviewed_pipeline as pipeline
from offline_reviewed_math_clip_export import probe
from test_offline_review_queue_math_handoff import fixture


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n")


class PipelineSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "session.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=160x90:rate=10:duration=5", "-c:v",
                        "libx264", "-pix_fmt", "yuv420p", str(self.video)],
                       check=True, timeout=30)
        self.sha = pipeline._sha(self.video)
        self.data = fixture()
        self.data["queue"]["source_recording_sha256_claim_unverified"] = self.sha
        self.data["queue"]["hands"][0]["source_recording_sha256_claim_unverified"] = self.sha
        self.data["bridge_input"]["reviewed_hand"]["source_recording_sha256_claim"] = self.sha
        self.queue = self.root / "review.json"
        self.annotation = self.root / "annotation.json"
        self.target = self.root / "results"
        self.approval = {"schema_version": 1, "source_kind": "synthetic_fixture",
                         "table_id": 2, "hand_label": "hand-42",
                         "reviewer_label": "synthetic-test", "start_seconds": 1,
                         "decision_seconds": 2, "end_seconds": 4,
                         "approved_for_export": True, "notes": "synthetic"}
        self.save()

    def save(self):
        write(self.queue, self.data)
        write(self.annotation, self.approval)

    def stub_bridge(self, candidate, output):
        """Fabricate a consistent math report to exercise the *real* clip exporter."""
        data = json.loads(Path(candidate).read_text())
        entries = data["weighted_range"]
        range_raw = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode()
        hand = data["reviewed_hand"]
        result = {"schema_version": 1,
                  "status": "offline_conditional_math_from_declared_review_and_range",
                  "blocked_reasons": [], "monte_carlo_recomputed": True,
                  "video_evidence_verified": False, "strategic_error_proven": False,
                  "automatic_clip_selection_authorized": False,
                  "input_sha256": pipeline._sha(candidate),
                  "variant": hand["variant"], "table_id": hand["table_id"],
                  "hand_label": hand["hand_label"],
                  "recording_sha256_claim_unverified": hand["source_recording_sha256_claim"],
                  "review_gate_claim": data["review_gate"],
                  "range_sha256": hashlib.sha256(range_raw).hexdigest(),
                  "range_combos_supplied": len(entries),
                  "trials_requested": 100, "seed": 42,
                  "wins": 50, "ties": 0, "losses": 50,
                  "equity": 0.5, "equity_ci95_hoeffding": [0.4, 0.6],
                  "ev_call_chips": 30.0, "ev_fold_chips": 0.0,
                  "ev_call_interval_chips": [16.0, 44.0],
                  "range_label_claim": hand["opponent_range"]["label"]}
        write(output, result)
        return result

    def run_stub(self):
        with patch.object(pipeline, "_bridge_export", side_effect=self.stub_bridge):
            return pipeline.run(self.video, self.queue, self.annotation, self.target)

    def test_real_mp4_and_provenance(self):
        result = self.run_stub()
        self.assertTrue(result["clip_exported"])
        self.assertFalse(result["video_evidence_verified"])
        self.assertEqual(result["source_recording_sha256_verified_bytes"], self.sha)
        duration, streams = probe(self.target / "clip.mp4")
        self.assertAlmostEqual(duration, 3, delta=0.3)
        self.assertTrue(any(x.get("codec_name") == "mov_text" for x in streams["streams"]))
        manifest = json.loads((self.target / "pipeline.json").read_text())
        for name, info in manifest["files"].items():
            self.assertEqual(info["sha256"], pipeline._sha(self.target / name))

    def test_blocked_review_does_not_run_math(self):
        self.data["manual_review"]["event_resolutions"][0]["outcome"] = "unresolved"
        self.save()
        with patch.object(pipeline, "_bridge_export") as bridge:
            result = pipeline.run(self.video, self.queue, self.annotation, self.target)
        bridge.assert_not_called()
        self.assertEqual(result["status"], "blocked_review")
        self.assertFalse((self.target / "candidate.json").exists())
        self.assertFalse((self.target / "clip.mp4").exists())

    def test_refuse_unapproved_clip(self):
        self.approval["approved_for_export"] = False
        self.save()
        with self.assertRaises(ValueError):
            self.run_stub()
        self.assertFalse(self.target.exists())

    def test_refuse_mismatched_video_hash(self):
        self.data["queue"]["source_recording_sha256_claim_unverified"] = "a" * 64
        self.data["queue"]["hands"][0]["source_recording_sha256_claim_unverified"] = "a" * 64
        self.data["bridge_input"]["reviewed_hand"]["source_recording_sha256_claim"] = "a" * 64
        self.save()
        with self.assertRaises(ValueError):
            self.run_stub()
        self.assertFalse(self.target.exists())

    def test_existing_directory_untouched(self):
        self.target.mkdir()
        (self.target / "keep").write_text("KEEP")
        with self.assertRaises(ValueError):
            self.run_stub()
        self.assertEqual((self.target / "keep").read_text(), "KEEP")

    def test_symlink_queue_rejected(self):
        link = self.root / "linked.json"
        link.symlink_to(self.queue)
        with self.assertRaises(ValueError):
            pipeline.run(self.video, link, self.annotation, self.target)
        self.assertFalse(self.target.exists())

    def test_ffmpeg_failure_does_not_publish(self):
        with patch.object(pipeline, "_bridge_export", side_effect=self.stub_bridge), \
             patch.object(pipeline, "_clip_export", side_effect=RuntimeError("ffmpeg")):
            with self.assertRaises(RuntimeError):
                pipeline.run(self.video, self.queue, self.annotation, self.target)
        self.assertFalse(self.target.exists())

    def test_plo6_table_four_blocked(self):
        self.data = fixture("PLO6", table=4)
        self.data["queue"]["source_recording_sha256_claim_unverified"] = self.sha
        self.data["queue"]["hands"][0]["source_recording_sha256_claim_unverified"] = self.sha
        self.data["bridge_input"]["reviewed_hand"]["source_recording_sha256_claim"] = self.sha
        self.data["manual_review"]["event_resolutions"][0]["outcome"] = "unresolved"
        self.save()
        result = pipeline.run(self.video, self.queue, self.annotation, self.target)
        self.assertEqual((result["variant"], result["table_id"]), ("PLO6", 4))
        self.assertEqual(result["status"], "blocked_review")

    def test_duplicate_json_keys_rejected(self):
        self.queue.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.run_stub()
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
