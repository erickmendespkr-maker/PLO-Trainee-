"""Synthetic tests for the offline review-to-math handoff; no poker clients."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_review_queue_math_handoff import analyze, export


def fixture(variant="PLO5", table=2, event_count=2):
    hero = ["Ac", "Kd", "Qh", "Js", "Tc"] + (["9d"] if variant == "PLO6" else [])
    villain = ["2d", "3h", "4s", "5c", "6d"] + (["7h"] if variant == "PLO6" else [])
    source = "a" * 64
    hand = {
        "variant": variant, "table_id": table, "hand_label": "hand-42",
        "source_recording_sha256_claim_unverified": source,
        "ledger_canonical_sha256": "b" * 64,
        "event_count": event_count, "unlinked_event_count": 0,
        "hand_review_flags": [], "temporal_audit_classification": None,
        "manual_review_required": True, "video_evidence_verified": False,
        "ocr_accuracy_verified": False, "equity_ev_authorized": False,
        "automatic_clip_selection_authorized": False,
        "events": [{"event_index": i, "review_reasons": [], "street": "flop"}
                   for i in range(event_count)],
    }
    return {
        "schema_version": 1,
        "queue": {
            "schema_version": 1,
            "status": "offline_human_review_priority_not_strategy_or_video_verification",
            "source_recording_sha256_claim_unverified": source,
            "hand_count": 1, "hands": [hand],
            "all_hands_require_manual_review": True,
            "video_evidence_verified": False, "ocr_accuracy_verified": False,
            "equity_ev_authorized": False, "automatic_clip_selection_authorized": False,
        },
        "hand_ref": {"table_id": table, "hand_label": "hand-42",
                     "ledger_canonical_sha256": "b" * 64},
        "manual_review": {
            "source_kind": "synthetic_fixture", "reviewer_label": "synthetic-test",
            "event_resolutions": [{"event_index": i, "outcome": "confirmed", "note": ""}
                                  for i in range(event_count)],
            "hand_flags_resolution": "not_applicable", "temporal_resolution": "not_applicable",
            "review_notes": "", "annotations_attested": True,
        },
        "bridge_input": {
            "schema_version": 1,
            "review_gate": {"status": "synthetic_fixture", "reviewer_label": "synthetic-test"},
            "reviewed_hand": {
                "schema_version": 1, "variant": variant, "table_id": table,
                "hand_label": "hand-42", "source_recording_sha256_claim": source,
                "annotation_source": "synthetic", "hero_cards": hero,
                "board_cards": ["8c", "8d", "8h"],
                "opponent_range": {"label": "hypothetical", "opponents": 1,
                                   "assumptions": ["synthetic declared range"]},
                "equity_estimate": None,
                "decision": {"action": "call", "pot_before_call": 100,
                             "call_cost": 40, "remaining_stack": 100,
                             "expected_rake": 0, "no_future_betting": True,
                             "no_side_pots": True},
                "unresolved_fields": [],
            },
            "weighted_range": [{"cards": villain, "weight": 1}],
            "monte_carlo": {"trials": 100, "seed": 42},
        },
    }


class HandoffTests(unittest.TestCase):
    def test_ready_synthetic_handoff_without_claiming_equity(self):
        a = analyze(fixture())
        self.assertEqual(a["status"], "handoff_candidate_requires_bridge_validation")
        self.assertEqual(a["events_reviewed_claim"], 2)
        self.assertIsNotNone(a["bridge_input_candidate"])
        for key in ("monte_carlo_executed", "video_evidence_verified",
                    "ocr_accuracy_verified", "strategic_error_proven",
                    "automatic_clip_selection_authorized"):
            self.assertFalse(a[key])
        self.assertEqual(a, analyze(fixture()))

    def test_four_table_metadata(self):
        for table in range(1, 5):
            with self.subTest(table=table):
                self.assertEqual(analyze(fixture(table=table))["table_id"], table)

    def test_plo6(self):
        self.assertEqual(analyze(fixture("PLO6"))["variant"], "PLO6")

    def test_missing_review_blocks(self):
        d = fixture()
        d["manual_review"]["event_resolutions"][0]["outcome"] = "unresolved"
        a = analyze(d)
        self.assertIn("unresolved_event_reviews", a["blocked_reasons"])
        self.assertIsNone(a["bridge_input_candidate"])

    def test_missing_event_resolution_rejected(self):
        d = fixture()
        d["manual_review"]["event_resolutions"].pop()
        with self.assertRaises(ValueError):
            analyze(d)

    def test_duplicate_event_index_rejected(self):
        d = fixture()
        d["manual_review"]["event_resolutions"][1]["event_index"] = 0
        with self.assertRaises(ValueError):
            analyze(d)

    def test_corrected_event_requires_note(self):
        d = fixture()
        d["manual_review"]["event_resolutions"][0]["outcome"] = "corrected"
        with self.assertRaises(ValueError):
            analyze(d)
        d["manual_review"]["event_resolutions"][0]["note"] = "Corrected amount"
        self.assertFalse(analyze(d)["blocked_reasons"])

    def test_unattested_blocks(self):
        d = fixture()
        d["manual_review"]["annotations_attested"] = False
        self.assertIn("annotations_not_attested", analyze(d)["blocked_reasons"])

    def test_hand_flags_require_explicit_resolution(self):
        d = fixture()
        d["queue"]["hands"][0]["hand_review_flags"] = ["uncertain-pot"]
        with self.assertRaises(ValueError):
            analyze(d)
        d["manual_review"]["hand_flags_resolution"] = "unresolved"
        self.assertIn("unresolved_hand_flags", analyze(d)["blocked_reasons"])
        d["manual_review"]["hand_flags_resolution"] = "resolved"
        with self.assertRaises(ValueError):
            analyze(d)
        d["manual_review"]["review_notes"] = "Reconciled with human transcript"
        self.assertEqual(analyze(d)["blocked_reasons"], [])

    def test_temporal_warning_requires_resolution(self):
        d = fixture()
        d["queue"]["hands"][0]["temporal_audit_classification"] = "possible_missing_terminal_frames"
        with self.assertRaises(ValueError):
            analyze(d)
        d["manual_review"]["temporal_resolution"] = "unresolved"
        self.assertIn("unresolved_temporal_diagnostics", analyze(d)["blocked_reasons"])
        d["manual_review"]["temporal_resolution"] = "resolved"
        d["manual_review"]["review_notes"] = "Reviewed tail frames manually"
        self.assertFalse(analyze(d)["blocked_reasons"])

    def test_unresolved_math_blocks(self):
        d = fixture()
        d["bridge_input"]["reviewed_hand"]["unresolved_fields"] = ["hero card unknown"]
        self.assertIn("unresolved_math_annotations", analyze(d)["blocked_reasons"])

    def test_no_future_betting_blocks(self):
        d = fixture()
        d["bridge_input"]["reviewed_hand"]["decision"]["no_future_betting"] = False
        self.assertIn("future_betting_not_modeled", analyze(d)["blocked_reasons"])

    def test_multiway_blocks(self):
        d = fixture()
        d["bridge_input"]["reviewed_hand"]["opponent_range"]["opponents"] = 2
        self.assertIn("only_heads_up_supported", analyze(d)["blocked_reasons"])

    def test_raise_blocks(self):
        d = fixture()
        d["bridge_input"]["reviewed_hand"]["decision"]["action"] = "raise"
        self.assertIn("only_call_vs_fold_supported", analyze(d)["blocked_reasons"])

    def test_side_pots_block(self):
        d = fixture()
        d["bridge_input"]["reviewed_hand"]["decision"]["no_side_pots"] = False
        self.assertIn("side_pots_not_modeled", analyze(d)["blocked_reasons"])

    def test_identity_mismatch_rejected(self):
        for field, value in (("variant", "PLO6"), ("table_id", 4),
                             ("hand_label", "other"),
                             ("source_recording_sha256_claim", "c" * 64)):
            with self.subTest(field=field):
                d = fixture()
                d["bridge_input"]["reviewed_hand"][field] = value
                with self.assertRaises(ValueError):
                    analyze(d)

    def test_ledger_digest_mismatch_rejected(self):
        d = fixture()
        d["hand_ref"]["ledger_canonical_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            analyze(d)

    def test_gate_mismatch_rejected(self):
        d = fixture()
        d["bridge_input"]["review_gate"]["reviewer_label"] = "someone else"
        with self.assertRaises(ValueError):
            analyze(d)

    def test_human_annotation_claim_still_unverified(self):
        d = fixture()
        d["manual_review"]["source_kind"] = "human_annotation_claim"
        d["bridge_input"]["review_gate"]["status"] = "human_confirmed_claim"
        d["bridge_input"]["reviewed_hand"]["annotation_source"] = "human_annotation"
        a = analyze(d)
        self.assertFalse(a["video_evidence_verified"])
        self.assertFalse(a["opponent_range_verified"])

    def test_overclaim_queue_rejected(self):
        d = fixture()
        d["queue"]["equity_ev_authorized"] = True
        with self.assertRaises(ValueError):
            analyze(d)

    def test_bool_table_rejected(self):
        d = fixture()
        d["hand_ref"]["table_id"] = True
        with self.assertRaises(ValueError):
            analyze(d)

    def test_extra_key_rejected(self):
        d = fixture()
        d["automatic_clips"] = True
        with self.assertRaises(ValueError):
            analyze(d)

    def test_export_candidate_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, report, candidate = (root / name for name in ("input.json", "report.json", "bridge.json"))
            src.write_text(json.dumps(fixture()))
            result = export(src, report, candidate)
            self.assertEqual(result["status"], "handoff_candidate_requires_bridge_validation")
            self.assertEqual(json.loads(candidate.read_text())["review_gate"]["status"], "synthetic_fixture")
            self.assertNotIn("bridge_input_candidate", json.loads(report.read_text()))
            with self.assertRaises(ValueError):
                export(src, report, candidate)

    def test_blocked_export_no_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, report, candidate = (root / name for name in ("input.json", "report.json", "bridge.json"))
            d = fixture()
            d["manual_review"]["event_resolutions"][0]["outcome"] = "unresolved"
            src.write_text(json.dumps(d))
            result = export(src, report, candidate)
            self.assertEqual(result["status"], "blocked_for_manual_review")
            self.assertTrue(report.exists())
            self.assertFalse(candidate.exists())

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, link = root / "input.json", root / "link.json"
            src.write_text(json.dumps(fixture()))
            link.symlink_to(src)
            with self.assertRaises(ValueError):
                export(link, root / "report.json", root / "bridge.json")

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.json"
            src.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):
                export(src, root / "report.json", root / "bridge.json")

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.json"
            src.write_text('{"schema_version":NaN}')
            with self.assertRaises(ValueError):
                export(src, root / "report.json", root / "bridge.json")


if __name__ == "__main__":
    unittest.main()
