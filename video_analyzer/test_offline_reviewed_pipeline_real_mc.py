"""Real offline PLO5/PLO6 Monte Carlo -> EV -> FFmpeg tests (no math stubs).

All recordings, hands, ranges and timestamps are synthetic, not OCR-verified.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_reviewed_pipeline as pipeline
from offline_reviewed_math_clip_export import inspect, probe
from test_offline_review_queue_math_handoff import fixture


def save(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class RealMonteCarloPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.video = self.root / "session.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.video)],
                       check=True, capture_output=True, timeout=30)
        self.hash = pipeline._sha(self.video)
        self.data = fixture()
        self.annotation = {"schema_version": 1, "source_kind": "synthetic_fixture",
                           "table_id": 2, "hand_label": "hand-42",
                           "reviewer_label": "synthetic-test", "start_seconds": 1,
                           "decision_seconds": 2, "end_seconds": 4,
                           "approved_for_export": True, "notes": "synthetic only"}
        self.queue, self.approval = self.root / "queue.json", self.root / "annotation.json"
        self.output = self.root / "results"
        self.persist()

    def persist(self):
        for obj in (self.data["queue"], self.data["queue"]["hands"][0]):
            obj["source_recording_sha256_claim_unverified"] = self.hash
        self.data["bridge_input"]["reviewed_hand"]["source_recording_sha256_claim"] = self.hash
        save(self.queue, self.data)
        save(self.approval, self.annotation)

    def run_real(self, output=None):
        return pipeline.run(self.video, self.queue, self.approval, output or self.output)

    def assert_real_clip(self, variant, table):
        result = self.run_real()
        self.assertTrue(result["monte_carlo_recomputed"] and result["clip_exported"])
        self.assertFalse(result["video_evidence_verified"])
        self.assertEqual((result["variant"], result["table_id"]), (variant, table))
        report = json.loads((self.output / "math.json").read_text())
        candidate = json.loads((self.output / "candidate.json").read_text())
        trials = candidate["monte_carlo"]["trials"]
        self.assertEqual(report["wins"] + report["ties"] + report["losses"], trials)
        self.assertEqual(report["equity"], (report["wins"] + .5 * report["ties"]) / trials)
        self.assertEqual(report["input_sha256"], pipeline._sha(self.output / "candidate.json"))
        clip = json.loads((self.output / "clip.json").read_text())
        self.assertEqual(clip["equity"], report["equity"])
        self.assertEqual(clip["clip_sha256"], pipeline._sha(self.output / "clip.mp4"))
        duration, meta = probe(self.output / "clip.mp4")
        self.assertAlmostEqual(duration, 3, delta=.3)
        self.assertTrue(any(s.get("codec_name") == "mov_text" for s in meta["streams"]))
        for name, info in json.loads((self.output / "pipeline.json").read_text())["files"].items():
            self.assertEqual(info["sha256"], pipeline._sha(self.output / name))
        return report

    def test_plo5_real_engine_and_mp4(self):
        self.assert_real_clip("PLO5", 2)

    def test_plo6_table_four_real_engine_and_mp4(self):
        self.data = fixture("PLO6", table=4)
        self.annotation["table_id"] = 4
        self.persist()
        self.assert_real_clip("PLO6", 4)

    def test_reproducible_math_seed(self):
        self.run_real()
        first = json.loads((self.output / "math.json").read_text())
        other = self.root / "again"
        self.run_real(other)
        self.assertEqual(first, json.loads((other / "math.json").read_text()))

    def test_card_collision_blocks_publication(self):
        self.data["bridge_input"]["weighted_range"][0]["cards"][0] = "Ac"
        self.persist()
        with self.assertRaises(ValueError):
            self.run_real()
        self.assertFalse(self.output.exists())

    def test_zero_weight_blocks_publication(self):
        self.data["bridge_input"]["weighted_range"][0]["weight"] = 0
        self.persist()
        with self.assertRaises(ValueError):
            self.run_real()
        self.assertFalse(self.output.exists())

    def test_unreviewed_event_blocks_math_and_clip(self):
        self.data["manual_review"]["event_resolutions"][0]["outcome"] = "unresolved"
        self.persist()
        result = self.run_real()
        self.assertEqual(result["status"], "blocked_review")
        self.assertFalse(result["monte_carlo_recomputed"])
        self.assertFalse((self.output / "math.json").exists())
        self.assertFalse((self.output / "clip.mp4").exists())

    def test_unapproved_clip_not_published(self):
        self.annotation["approved_for_export"] = False
        self.persist()
        with self.assertRaises(ValueError):
            self.run_real()
        self.assertFalse(self.output.exists())

    def test_tampered_outcome_counts_rejected(self):
        self.run_real()
        load = lambda name: json.loads((self.output / name).read_text())
        handoff, candidate, report, annotation = (load(n) for n in
            ("handoff.json", "candidate.json", "math.json", "annotation_input.json"))
        report.update({"wins": 100, "ties": 0, "losses": 0})
        if report["equity"] == 1:
            report.update({"wins": 0, "losses": 100})
        with self.assertRaisesRegex(ValueError, "Equity inconsistent"):
            inspect(handoff, candidate, pipeline._sha(self.output / "candidate.json"),
                    report, annotation, self.hash, 5)


if __name__ == "__main__":
    unittest.main()
