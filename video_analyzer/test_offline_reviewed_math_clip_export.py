"""Synthetic offline clip export tests; no live poker client or actual video OCR."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_review_queue_math_handoff import analyze as handoff_analyze
from test_offline_review_queue_math_handoff import fixture
from offline_reviewed_math_clip_export import export, inspect, probe, source_sha


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "session.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=160x90:rate=10:duration=5", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(self.video)], check=True, timeout=20)
        self.source_hash = source_sha(self.video)
        payload = fixture()
        payload["queue"]["source_recording_sha256_claim_unverified"] = self.source_hash
        payload["queue"]["hands"][0]["source_recording_sha256_claim_unverified"] = self.source_hash
        payload["bridge_input"]["reviewed_hand"]["source_recording_sha256_claim"] = self.source_hash
        handoff = handoff_analyze(payload)
        self.candidate = handoff.pop("bridge_input_candidate")
        self.handoff = handoff
        self.handoff_path = self.root / "handoff.json"
        self.candidate_path = self.root / "candidate.json"
        self.math_path = self.root / "math.json"
        self.annotation_path = self.root / "annotation.json"
        write_json(self.handoff_path, self.handoff)
        write_json(self.candidate_path, self.candidate)
        entries = self.candidate["weighted_range"]
        range_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode()
        self.math = {
            "schema_version": 1, "status": "offline_conditional_math_from_declared_review_and_range",
            "blocked_reasons": [], "monte_carlo_recomputed": True,
            "video_evidence_verified": False, "strategic_error_proven": False,
            "automatic_clip_selection_authorized": False,
            "input_sha256": source_sha(self.candidate_path),
            "variant": "PLO5", "table_id": 2, "hand_label": "hand-42",
            "recording_sha256_claim_unverified": self.source_hash,
            "review_gate_claim": self.candidate["review_gate"],
            "range_sha256": hashlib.sha256(range_bytes).hexdigest(),
            "range_combos_supplied": 1, "trials_requested": 100, "seed": 42,
            "wins": 50, "ties": 0, "losses": 50,
            "equity": 0.5, "equity_ci95_hoeffding": [0.4, 0.6],
            "ev_call_chips": 30.0, "ev_fold_chips": 0.0,
            "ev_call_interval_chips": [16.0, 44.0],
            "range_label_claim": "hypothetical",
        }
        self.annotation = {
            "schema_version": 1, "source_kind": "synthetic_fixture", "table_id": 2,
            "hand_label": "hand-42", "reviewer_label": "synthetic-test",
            "start_seconds": 1.0, "decision_seconds": 2.0, "end_seconds": 4.0,
            "approved_for_export": True, "notes": "Synthetic, not a real hand",
        }
        self.save()

    def save(self):
        write_json(self.math_path, self.math)
        write_json(self.annotation_path, self.annotation)

    def run_export(self):
        return export(self.video, self.handoff_path, self.candidate_path,
                      self.math_path, self.annotation_path, self.root / "clip42")

    def test_real_ffmpeg_mp4_has_embedded_subtitle_and_hash(self):
        result = self.run_export()
        mp4 = self.root / "clip42.mp4"
        self.assertTrue(mp4.exists())
        self.assertEqual(result["clip_sha256"], source_sha(mp4))
        self.assertEqual(result["source_recording_sha256_verified_bytes"], self.source_hash)
        self.assertEqual(result["embedded_subtitle_codec"], "mov_text")
        duration, meta = probe(mp4)
        self.assertAlmostEqual(duration, 3, delta=0.3)
        self.assertTrue(any(s.get("codec_name") == "mov_text" for s in meta["streams"]))
        self.assertIn("Range hipotético", (self.root / "clip42.srt").read_text())
        self.assertFalse(result["status"].endswith("video_verified"))

    def test_no_overwrite(self):
        self.run_export()
        original = (self.root / "clip42.mp4").read_bytes()
        with self.assertRaises(ValueError):
            self.run_export()
        self.assertEqual((self.root / "clip42.mp4").read_bytes(), original)

    def test_source_hash_tampering(self):
        self.handoff["source_recording_sha256_claim_unverified"] = "a" * 64
        write_json(self.handoff_path, self.handoff)
        with self.assertRaisesRegex(ValueError, "Recording hash mismatch"):
            self.run_export()

    def test_math_not_bound_to_candidate(self):
        self.math["input_sha256"] = "b" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "exact candidate"):
            self.run_export()

    def test_math_wrong_ev(self):
        self.math["ev_call_chips"] = 999
        self.save()
        with self.assertRaisesRegex(ValueError, "Inconsistent EV"):
            self.run_export()

    def test_math_wrong_range_digest(self):
        self.math["range_sha256"] = "c" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "Monte Carlo input"):
            self.run_export()

    def test_math_blocked(self):
        self.math["blocked_reasons"] = ["unresolved_annotations"]
        self.save()
        with self.assertRaisesRegex(ValueError, "Math report"):
            self.run_export()

    def test_math_not_computed(self):
        self.math["monte_carlo_recomputed"] = False
        self.save()
        with self.assertRaises(ValueError):
            self.run_export()

    def test_math_overclaim(self):
        self.math["strategic_error_proven"] = True
        self.save()
        with self.assertRaises(ValueError):
            self.run_export()

    def test_bad_outcome_counts(self):
        self.math["wins"] = 60
        self.save()
        with self.assertRaisesRegex(ValueError, "outcome counts"):
            self.run_export()

    def test_wrong_table(self):
        self.annotation["table_id"] = 3
        self.save()
        with self.assertRaisesRegex(ValueError, "not explicitly approved"):
            self.run_export()

    def test_approval_required(self):
        self.annotation["approved_for_export"] = False
        self.save()
        with self.assertRaises(ValueError):
            self.run_export()

    def test_bounds(self):
        for start, moment, end in ((0, 2, 7), (3, 2, 4), (1, 2, 1.5), (-1, 2, 4)):
            with self.subTest(times=(start, moment, end)):
                self.annotation.update(start_seconds=start, decision_seconds=moment,
                                       end_seconds=end)
                self.save()
                with self.assertRaisesRegex(ValueError, "time window"):
                    self.run_export()

    def test_nan_timestamp(self):
        self.annotation["start_seconds"] = float("nan")
        self.save()
        with self.assertRaises(ValueError):
            self.run_export()

    def test_duplicate_json_keys(self):
        self.annotation_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            self.run_export()

    def test_symlink_source(self):
        link = self.root / "linked.mp4"
        link.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, "Unsafe recording"):
            export(link, self.handoff_path, self.candidate_path, self.math_path,
                   self.annotation_path, self.root / "clip42")

    def test_symlink_json(self):
        link = self.root / "linked.json"
        link.symlink_to(self.math_path)
        with self.assertRaisesRegex(ValueError, "Unsafe JSON"):
            export(self.video, self.handoff_path, self.candidate_path, link,
                   self.annotation_path, self.root / "clip42")

    def test_invalid_output_name(self):
        with self.assertRaisesRegex(ValueError, "Unsafe output stem"):
            export(self.video, self.handoff_path, self.candidate_path,
                   self.math_path, self.annotation_path, self.root / "bad name")

    def test_video_unchanged_on_failure(self):
        before = source_sha(self.video)
        self.math["ev_call_chips"] = -1
        self.save()
        with self.assertRaises(ValueError):
            self.run_export()
        self.assertEqual(source_sha(self.video), before)
        self.assertFalse((self.root / "clip42.mp4").exists())


if __name__ == "__main__":
    unittest.main()