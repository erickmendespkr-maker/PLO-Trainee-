"""Synthetic-only tests for source-bound human correction proposals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_hand_correction_overlay import build_overlay, digest, export_overlay, read_json


def fixture():
    entry = {"table_id": 1, "hand_label_human_assigned": "h1",
             "variant": "PLO5", "hero_cards": None, "board_by_street": {"flop": None, "turn": None, "river": None},
             "actions": [], "pot_before_decision": None, "call_amount": None,
             "effective_stack": None, "source_pts_start_seconds": None,
             "source_pts_end_seconds": None, "opponent_range_notes": "", "notes": "",
             "confidence_subjective": 0.3}
    row = {"table_id": 1, "hand_label_human_assigned": "h1", "human_entry": entry,
           "hand_reconstruction_verified": False, "ready_for_equity_or_ev": False,
           "automatic_clip_selection_authorized": False}
    draft = {"schema_version": 1, "analysis_status": "human_entered_hand_history_drafts_no_math",
             "job_id": "a" * 32, "source_sha256": "b" * 64, "hands": [row],
             "hand_start_or_end_pts_verified": False, "hand_reconstruction_verified": False,
             "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False}
    sub = {"schema_version": 1, "job_id": draft["job_id"],
           "source_draft_sha256": digest(draft), "reviewer_label": "analista",
           "corrections": [{"table_id": 1, "hand_label_human_assigned": "h1",
                            "field": "hero_cards", "expected_value_sha256": digest(None),
                            "proposed_value": ["As", "Kh", "Qd", "Jc", "Tc"],
                            "reason": "Cartas anotadas manualmente", "confidence_subjective": 0.65}]}
    return draft, sub


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.draft, self.sub = fixture()

    def build(self):
        return build_overlay(self.draft, self.sub)

    def test_happy_path_is_pending_not_verified(self):
        result = self.build()
        self.assertEqual(result["counts"], {"pending": 1, "accepted": 0})
        self.assertFalse(result["ready_for_equity_or_ev"])
        self.assertFalse(result["automatic_clip_selection_authorized"])
        self.assertEqual(result["corrections"][0]["review_state"], "pending_independent_review")
        self.assertIsNone(self.draft["hands"][0]["human_entry"]["hero_cards"])

    def test_stale_source_digest(self):
        self.sub["source_draft_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "bound"):
            self.build()

    def test_stale_field_digest(self):
        self.sub["corrections"][0]["expected_value_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.build()

    def test_wrong_hand(self):
        self.sub["corrections"][0]["hand_label_human_assigned"] = "h2"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.build()

    def test_cross_table(self):
        self.sub["corrections"][0]["table_id"] = 2
        with self.assertRaises(ValueError):
            self.build()

    def test_duplicate_correction(self):
        self.sub["corrections"].append(copy.deepcopy(self.sub["corrections"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()

    def test_unknown_field(self):
        self.sub["corrections"][0]["field"] = "ready_for_equity_or_ev"
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_noop(self):
        e = self.sub["corrections"][0]
        e["proposed_value"] = None
        with self.assertRaisesRegex(ValueError, "No-op"):
            self.build()

    def test_wrong_variant_card_count(self):
        self.sub["corrections"][0]["proposed_value"].append("9h")
        with self.assertRaisesRegex(ValueError, "variant"):
            self.build()

    def test_invalid_cards(self):
        self.sub["corrections"][0]["proposed_value"] = ["As"] * 5
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_nan_confidence(self):
        self.sub["corrections"][0]["confidence_subjective"] = float("nan")
        with self.assertRaises(ValueError):
            self.build()

    def test_upstream_verification_claim_rejected(self):
        self.draft["hand_reconstruction_verified"] = True
        self.sub["source_draft_sha256"] = digest(self.draft)
        with self.assertRaisesRegex(ValueError, "verification"):
            self.build()

    def test_wrong_job(self):
        self.sub["job_id"] = "f" * 32
        with self.assertRaises(ValueError):
            self.build()

    def test_bad_pts(self):
        e = self.sub["corrections"][0]
        e["field"] = "source_pts_start_seconds"
        e["proposed_value"] = -1
        with self.assertRaises(ValueError):
            self.build()

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dup.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_json(p)

    def test_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b, c = (root / s for s in ("draft.json", "input.json", "output.json"))
            a.write_text(json.dumps(self.draft))
            b.write_text(json.dumps(self.sub))
            report = export_overlay(a, b, c)
            self.assertEqual(json.loads(c.read_text())["status"], report["status"])
            with self.assertRaises(ValueError):
                export_overlay(a, b, c)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "draft.json"
            p.write_text(json.dumps(self.draft))
            link = root / "link.json"
            link.symlink_to(p)
            with self.assertRaises(ValueError):
                read_json(link)

    def test_invalid_action(self):
        e = self.sub["corrections"][0]
        e["field"] = "actions"
        e["expected_value_sha256"] = digest([])
        e["proposed_value"] = [{"street": "flop", "actor": "villain_1", "action": "hack",
                                 "amount": 2, "source_pts_seconds": 1}]
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_board(self):
        e = self.sub["corrections"][0]
        e["field"] = "board_by_street"
        e["expected_value_sha256"] = digest(self.draft["hands"][0]["human_entry"]["board_by_street"])
        e["proposed_value"] = {"flop": None, "turn": "As", "river": None}
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_oversized_notes(self):
        e = self.sub["corrections"][0]
        e["field"] = "notes"
        e["expected_value_sha256"] = digest("")
        e["proposed_value"] = "x" * 2001
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
