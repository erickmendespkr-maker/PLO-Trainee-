"""Synthetic-only tests for offline action-to-crop evidence linkage."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_action_evidence_link import export, link, read_json
from offline_street_contribution_ledger import reconstruct


class EvidenceLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.crops = self.root / "crops"
        self.crops.mkdir()
        self.crop = self.crops / "frame.png"
        self.crop.write_bytes(b"synthetic-image-bytes-not-real-png")
        self.sha = hashlib.sha256(self.crop.read_bytes()).hexdigest()
        self.input = {
            "schema_version": 1, "variant": "PLO5", "source": "synthetic",
            "table_id": 1, "hand_label": "synthetic-hand-1",
            "initial_stacks": {"A": 200, "B": 200}, "starting_pot": 0,
            "events": [
                {"street": "preflop", "actor": "A", "kind": "post_blind", "delta_chips": 1,
                 "source_pts_seconds": 10.0, "confidence": 0.95, "evidence": "synthetic",
                 "min_full_raise_increment": None},
                {"street": "preflop", "actor": "B", "kind": "post_blind", "delta_chips": 2,
                 "source_pts_seconds": 11.0, "confidence": 0.85, "evidence": "synthetic",
                 "min_full_raise_increment": None},
                {"street": "preflop", "actor": "A", "kind": "fold", "delta_chips": 0,
                 "source_pts_seconds": 12.0, "confidence": 0.8, "evidence": "synthetic",
                 "min_full_raise_increment": None},
            ],
        }
        self.ledger = reconstruct(self.input)
        self.manifest = {
            "schema_version": 1, "source_recording_sha256": "a" * 64,
            "source_duration_seconds": 100.0,
            "ledger_input_canonical_sha256": self.ledger["input_canonical_sha256"],
            "table_id": 1, "hand_label": "synthetic-hand-1",
            "observations": [{
                "event_index": 0, "frame_pts_seconds": 10.1,
                "crop_path": "frame.png", "crop_sha256": self.sha,
                "bbox_pixels": [10, 20, 100, 50], "recognition_confidence": 0.7,
                "extraction_method": "synthetic",
            }],
        }

    def test_links_and_preserves_uncertainty(self):
        report = link(self.ledger, self.manifest, self.crops)
        self.assertEqual(report["linked_count"], 1)
        self.assertEqual(report["unlinked_event_indices"], [1, 2])
        self.assertEqual(report["linked_observations"][0]["pts_difference_seconds"], 0.1)
        self.assertFalse(report["video_evidence_verified"])
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["automatic_clip_selection_authorized"])
        self.assertFalse(report["linked_observations"][0]["source_recording_frame_verified"])

    def test_all_events_linked_does_not_certify(self):
        for i in (1, 2):
            entry = copy.deepcopy(self.manifest["observations"][0])
            entry["event_index"] = i
            entry["frame_pts_seconds"] = float(10 + i)
            self.manifest["observations"].append(entry)
        report = link(self.ledger, self.manifest, self.crops)
        self.assertEqual(report["unlinked_event_indices"], [])
        self.assertFalse(report["video_evidence_verified"])

    def test_empty_manifest(self):
        self.manifest["observations"] = []
        self.assertEqual(link(self.ledger, self.manifest, self.crops)["unlinked_event_indices"], [0, 1, 2])

    def test_sha_tampering(self):
        self.crop.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            link(self.ledger, self.manifest, self.crops)

    def test_ledger_digest_mismatch(self):
        self.manifest["ledger_input_canonical_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_table_mismatch(self):
        self.manifest["table_id"] = 2
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_hand_mismatch(self):
        self.manifest["hand_label"] = "other"
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_duplicate_event_index(self):
        self.manifest["observations"].append(copy.deepcopy(self.manifest["observations"][0]))
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_event_index_out_of_bounds(self):
        self.manifest["observations"][0]["event_index"] = 3
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_timestamp_mismatch(self):
        self.manifest["observations"][0]["frame_pts_seconds"] = 15.0
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_timestamp_after_duration(self):
        self.manifest["source_duration_seconds"] = 9
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_invalid_bbox(self):
        self.manifest["observations"][0]["bbox_pixels"] = [0, 0, 0, 100]
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_nan_confidence(self):
        self.manifest["observations"][0]["recognition_confidence"] = float("nan")
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_bool_confidence(self):
        self.manifest["observations"][0]["recognition_confidence"] = True
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_parent_traversal_rejected(self):
        self.manifest["observations"][0]["crop_path"] = "../frame.png"
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_symlink_crop_rejected(self):
        symlink = self.crops / "linked.png"
        symlink.symlink_to(self.crop)
        self.manifest["observations"][0]["crop_path"] = "linked.png"
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_symlink_directory_rejected(self):
        (self.crops / "sub").symlink_to(self.root, target_is_directory=True)
        self.manifest["observations"][0]["crop_path"] = "sub/frame.png"
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_duplicate_json_key_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            read_json(path)

    def test_exclusive_export_and_roundtrip(self):
        lp, mp, out = (self.root / name for name in ("ledger.json", "manifest.json", "result.json"))
        lp.write_text(json.dumps(self.ledger), encoding="utf-8")
        mp.write_text(json.dumps(self.manifest), encoding="utf-8")
        result = export(lp, mp, self.crops, out)
        self.assertEqual(json.loads(out.read_text())["linked_count"], result["linked_count"])
        with self.assertRaisesRegex(ValueError, "Unsafe output"):
            export(lp, mp, self.crops, out)

    def test_report_is_not_raw_ledger(self):
        with self.assertRaises(ValueError):
            link(self.input, self.manifest, self.crops)

    def test_schema_rejects_extra_field(self):
        self.manifest["unverified_flag"] = True
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)

    def test_pseudo_sha_rejected(self):
        self.manifest["source_recording_sha256"] = "A" * 64
        with self.assertRaises(ValueError):
            link(self.ledger, self.manifest, self.crops)


if __name__ == "__main__":
    unittest.main()
