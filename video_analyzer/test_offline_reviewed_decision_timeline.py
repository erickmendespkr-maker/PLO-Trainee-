"""Synthetic file-integrity and declared-timestamp tests; no real poker video."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_reviewed_decision_timeline import build_index, export, load_result


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DecisionTimelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = "a" * 64
        self.dirs = []

    def make(self, name="hand1", table=1, label="h1", moment=2.0,
             blocked=False, variant="PLO5", source=None):
        folder = self.root / name
        folder.mkdir()
        source = source or self.source
        files = {
            "review_input.json": {"queue": "synthetic"},
            "annotation_input.json": {"schema_version": 1, "table_id": table,
                                      "hand_label": label, "start_seconds": moment-1,
                                      "decision_seconds": moment, "end_seconds": moment+1,
                                      "approved_for_export": True},
            "handoff.json": {"table_id": table, "hand_label": label,
                             "variant": variant,
                             "source_recording_sha256_claim_unverified": source},
        }
        status = "blocked_review" if blocked else "offline_conditional_math_and_approved_clip_exported"
        if not blocked:
            candidate = b'{"synthetic":true}\n'
            files.update({
                "candidate.json": candidate,
                "math.json": {"table_id": table, "hand_label": label, "variant": variant,
                              "input_sha256": sha(candidate), "monte_carlo_recomputed": True,
                              "equity": .5, "ev_call_chips": 30.0},
                "clip.mp4": b"synthetic-only-not-an-actual-mp4",
                "clip.srt": b"1\n00:00:00,000 --> 00:00:02,000\nSynthetic\n",
                "clip.json": {"table_id": table, "hand_label": label, "variant": variant,
                              "source_recording_sha256_verified_bytes": source,
                              "clip_sha256": sha(b"synthetic-only-not-an-actual-mp4"),
                              "bridge_input_sha256_verified_bytes": sha(candidate),
                              "clip_explanation_is_conditional": True,
                              "start_seconds": moment-1, "decision_seconds": moment,
                              "end_seconds": moment+1, "equity": .5,
                              "ev_call_chips": 30.0},
            })
        manifest = {"schema_version": 1, "status": status,
                    "table_id": table, "hand_label": label, "variant": variant,
                    "review_input_sha256": None, "annotation_input_sha256": None,
                    "clip_exported": not blocked, "monte_carlo_recomputed": not blocked,
                    "clip_sha256": sha(b"synthetic-only-not-an-actual-mp4") if not blocked else None,
                    "source_recording_sha256_verified_bytes": source if not blocked else None,
                    "blocked_reasons": ["unresolved_review"] if blocked else [],
                    "video_evidence_verified": False, "ocr_accuracy_verified": False,
                    "opponent_range_verified": False, "strategic_error_proven": False,
                    "automatic_clip_selection_authorized": False, "files": {}}
        for filename, value in files.items():
            data = (json.dumps(value, sort_keys=True).encode() + b"\n") if not isinstance(value, bytes) else value
            (folder / filename).write_bytes(data)
            manifest["files"][filename] = {"sha256": sha(data), "bytes": len(data)}
        for name in ("review_input.json", "annotation_input.json"):
            manifest[name.replace(".json", "") + "_sha256"] = manifest["files"][name]["sha256"]
        (folder / "pipeline.json").write_text(json.dumps(manifest) + "\n")
        self.dirs.append(folder)
        return folder

    def rewrite(self, folder, name, mutate):
        path = folder / name
        data = json.loads(path.read_text())
        mutate(data)
        raw = json.dumps(data).encode() + b"\n"
        path.write_bytes(raw)
        if name != "pipeline.json":
            manifest = json.loads((folder / "pipeline.json").read_text())
            manifest["files"][name] = {"sha256": sha(raw), "bytes": len(raw)}
            (folder / "pipeline.json").write_text(json.dumps(manifest))

    def test_success_and_blocked_sorted(self):
        self.make("later", 4, "later", 5)
        self.make("blocked", 3, "blocked", 7, blocked=True)
        self.make("early", 1, "early", 2, variant="PLO6")
        index = build_index(self.dirs)
        self.assertEqual([r["result_directory"] for r in index["hands"]],
                         ["early", "later", "blocked"])
        self.assertEqual((index["exported_clip_count"], index["blocked_count"]), (2, 1))
        self.assertFalse(index["automatic_clip_selection_authorized"])
        self.assertFalse(index["timestamp_pts_verified"])
        self.assertEqual(index["source_recording_sha256_verified_for_exported_clips"], self.source)

    def test_export_create_only_and_deterministic(self):
        self.make()
        out = self.root / "timeline.json"
        first = export(self.dirs, out)
        self.assertEqual(first, json.loads(out.read_text()))
        saved = out.read_bytes()
        with self.assertRaises(ValueError): export(self.dirs, out)
        self.assertEqual(out.read_bytes(), saved)

    def test_overlapping_same_table_warning(self):
        self.make("one", 1, "one", 2)
        self.make("two", 1, "two", 2.5)
        self.make("other", 2, "other", 2.5)
        result = build_index(self.dirs)
        self.assertEqual(result["same_table_clip_window_overlaps_review_only"], [["one", "two"]])

    def test_reject_tampered_clip_bytes(self):
        folder = self.make()
        (folder / "clip.mp4").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"): build_index(self.dirs)

    def test_reject_tampered_json(self):
        folder = self.make()
        (folder / "math.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "digest mismatch"): build_index(self.dirs)

    def test_reject_math_candidate_hash_mismatch(self):
        folder = self.make()
        self.rewrite(folder, "math.json", lambda d: d.update(input_sha256="f"*64))
        with self.assertRaisesRegex(ValueError, "provenance mismatch"): build_index(self.dirs)

    def test_reject_unauthorized_timestamp(self):
        folder = self.make()
        self.rewrite(folder, "annotation_input.json", lambda d: d.update(decision_seconds=1.5))
        # Keep the pipeline snapshot digest consistent to isolate timestamp validation.
        self.rewrite(folder, "pipeline.json", lambda d: d.update(annotation_input_sha256=d["files"]["annotation_input.json"]["sha256"]))
        with self.assertRaisesRegex(ValueError, "timestamp association"): build_index(self.dirs)

    def test_reject_mixed_recordings(self):
        self.make("first", 1, "h1", 2)
        self.make("second", 2, "h2", 4, source="b"*64)
        with self.assertRaisesRegex(ValueError, "Multiple recording"): build_index(self.dirs)

    def test_reject_duplicate_hand(self):
        self.make("first", 1, "h1", 2)
        self.make("second", 1, "h1", 4)
        with self.assertRaisesRegex(ValueError, "Duplicate table/hand"): build_index(self.dirs)

    def test_reject_unexpected_file(self):
        folder = self.make()
        (folder / "untracked.txt").write_text("oops")
        with self.assertRaisesRegex(ValueError, "Unexpected or missing"): build_index(self.dirs)

    def test_reject_symlink_clip(self):
        folder = self.make()
        clip = folder / "clip.mp4"
        backup = self.root / "backup.mp4"
        backup.write_bytes(clip.read_bytes())
        clip.unlink()
        clip.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "Symlink input"): build_index(self.dirs)

    def test_reject_overclaim(self):
        folder = self.make()
        self.rewrite(folder, "pipeline.json", lambda d: d.update(video_evidence_verified=True))
        with self.assertRaisesRegex(ValueError, "verification claim"): build_index(self.dirs)

    def test_reject_blocked_clip(self):
        folder = self.make(blocked=True)
        (folder / "clip.mp4").write_bytes(b"bad")
        with self.assertRaises(ValueError): build_index(self.dirs)

    def test_reject_duplicate_json_keys(self):
        folder = self.make()
        (folder / "pipeline.json").write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"): build_index(self.dirs)

    def test_reject_nonfinite_json(self):
        folder = self.make()
        (folder / "pipeline.json").write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, "Nonfinite JSON"): build_index(self.dirs)

    def test_reject_overflow_json_float(self):
        folder = self.make()
        (folder / "pipeline.json").write_text('{"schema_version":1e999}')
        with self.assertRaisesRegex(ValueError, "Nonfinite JSON"): build_index(self.dirs)

    def test_reject_blocked_hand_from_other_recording(self):
        self.make("success", 1, "h1", 2)
        self.make("blocked", 2, "h2", 4, blocked=True, source="b"*64)
        with self.assertRaisesRegex(ValueError, "Multiple recording"): build_index(self.dirs)

    def test_reject_repeated_directories(self):
        folder = self.make()
        with self.assertRaisesRegex(ValueError, "Repeated pipeline"): build_index([folder, folder])

    def test_reject_more_than_forty(self):
        with self.assertRaisesRegex(ValueError, "1–40"): build_index([self.root]*41)

    def test_reject_export_outside_parent(self):
        self.make()
        other = self.root / "elsewhere"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "beside pipeline"): export(self.dirs, other / "timeline.json")


if __name__ == "__main__":
    unittest.main()
