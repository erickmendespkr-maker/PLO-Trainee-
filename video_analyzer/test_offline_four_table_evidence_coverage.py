"""Offline synthetic cross-stage provenance tests; never uses real poker or network."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import offline_four_table_evidence_coverage as mod
import offline_four_table_stack_sidepot_audit as stackmod

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class EvidenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.review = self.root / "review.json"
        self.pot = self.root / "pot.json"
        self.seats = self.root / "seats.json"
        self.stack = self.root / "stack.json"
        self.output = self.root / "coverage.json"
        self.review.write_bytes((FIXTURES / "cycle154_reviewed_actions.json").read_bytes())
        self.review_data = json.loads(self.review.read_text())
        self.pot_data = json.loads((FIXTURES / "cycle154_pot_gap.json").read_text())
        self.pot_data["source_betting_review_sha256"] = stackmod.sha256(self.review)
        self.save_pot()
        self.seat_data = json.loads((FIXTURES / "cycle154_seat_manifest.json").read_text())
        self.seat_data["source_pot_audit_sha256"] = stackmod.sha256(self.pot)
        self.save_seats()
        stackmod.audit(self.pot, self.seats, self.stack)
        self.stack_data = json.loads(self.stack.read_text())

    def save_pot(self):
        self.pot.write_text(json.dumps(self.pot_data), encoding="utf-8")

    def save_seats(self):
        self.seats.write_text(json.dumps(self.seat_data), encoding="utf-8")

    def save_stack(self):
        self.stack.write_text(json.dumps(self.stack_data), encoding="utf-8")

    def run_audit(self, **kwargs):
        return mod.audit(self.review, self.pot, self.seats, self.stack, self.output, **kwargs)

    def rejected(self, **kwargs):
        with self.assertRaises(ValueError):
            self.run_audit(**kwargs)
        self.assertFalse(self.output.exists())

    def test_four_table_reports_are_fail_closed(self):
        result = self.run_audit()
        self.assertEqual(len(result["hands"]), 4)
        self.assertEqual({x["table_id"] for x in result["hands"]}, {1, 2, 3, 4})
        self.assertFalse(result["ready_for_equity_or_ev"])
        self.assertFalse(result["automatic_clip_selection_authorized"])
        self.assertTrue(all(not x["action_history_complete"] for x in result["hands"]))

    def test_source_hashes_bound(self):
        result = self.run_audit()
        for key, path in (("source_betting_review_sha256", self.review),
                          ("source_pot_audit_sha256", self.pot),
                          ("source_seat_manifest_sha256", self.seats),
                          ("source_stack_audit_sha256", self.stack)):
            self.assertEqual(result[key], stackmod.sha256(path))

    def test_actions_preserve_timestamp_and_index(self):
        result = self.run_audit()
        a = result["hands"][0]["reviewed_action_evidence"][0]
        self.assertEqual(a["source_observation_index"], 1)
        self.assertEqual(a["pts_seconds"], 2.0)
        self.assertFalse(a["independent_visual_verification"])

    def test_seat_ledger_disagreement_flagged(self):
        h = self.run_audit()["hands"][0]
        self.assertIn("seat_net_contribution_not_reconciled_with_reviewed_actions", h["blockers"])
        hero = next(x for x in h["seat_coverage"] if x["actor"] == "hero")
        self.assertEqual(mod.Decimal(hero["unexplained_seat_minus_observed"]), mod.Decimal("-45.50"))

    def test_all_in_not_observed_flagged(self):
        self.assertIn("all_in_state_without_observed_all_in_label", self.run_audit()["hands"][0]["blockers"])

    def test_manual_pot_adjustments_flagged(self):
        self.assertIn("manual_pot_adjustments_not_tied_to_visual_timestamps", self.run_audit()["hands"][0]["blockers"])

    def test_long_gaps_are_not_inferred_actions(self):
        h = self.run_audit(gap_seconds=2.0)["hands"][0]
        self.assertEqual(len(h["long_intervals_between_reviewed_actions"]), 3)
        self.assertIn("long_interval_without_reviewed_action_not_proof_of_missing_action", h["blockers"])

    def test_default_threshold_no_gap_for_hand_one(self):
        self.assertEqual(self.run_audit()["hands"][0]["long_intervals_between_reviewed_actions"], [])

    def test_recording_unchecked_without_file(self):
        self.assertFalse(self.run_audit()["recording_hash_checked_in_this_run"])

    def test_recording_mismatch_rejected(self):
        rec = self.root / "video.mp4"
        rec.write_bytes(b"not the recorded video")
        self.rejected(recording_path=rec)

    def test_invalid_gap_zero(self):
        self.rejected(gap_seconds=0)

    def test_invalid_gap_nan(self):
        self.rejected(gap_seconds=float("nan"))

    def test_invalid_gap_bool(self):
        self.rejected(gap_seconds=True)

    def test_invalid_gap_huge(self):
        self.rejected(gap_seconds=3601)

    def test_existing_output_not_overwritten(self):
        self.output.write_text("keep")
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertEqual(self.output.read_text(), "keep")

    def test_symlink_source_rejected(self):
        link = self.root / "linked_review.json"
        link.symlink_to(self.review)
        with self.assertRaises(ValueError):
            mod.audit(link, self.pot, self.seats, self.stack, self.output)
        self.assertFalse(self.output.exists())

    def test_tampered_review_sha_rejected(self):
        self.review.write_text(self.review.read_text() + " ")
        self.rejected()

    def test_tampered_pot_sha_rejected(self):
        self.pot.write_text(self.pot.read_text() + " ")
        self.rejected()

    def test_tampered_seat_manifest_sha_rejected(self):
        self.seats.write_text(self.seats.read_text() + " ")
        self.rejected()

    def test_tampered_stack_status_rejected(self):
        self.stack_data["ready_for_equity_or_ev"] = True
        self.save_stack()
        self.rejected()

    def test_tampered_stack_tier_rejected(self):
        self.stack_data["hands"][0]["side_pot_tiers_conditional"][0]["amount"] = "600"
        self.save_stack()
        self.rejected()

    def test_tampered_stack_seat_total_rejected(self):
        self.stack_data["hands"][0]["net_seat_contributions"] = "70"
        self.stack_data["hands"][0]["conditional_contribution_difference"] = "2.50"
        self.save_stack()
        self.rejected()

    def test_cross_stage_table_mismatch_rejected(self):
        self.stack_data["hands"][0]["table_id"] = 4
        self.save_stack()
        self.rejected()

    def test_duplicate_seat_actor_rejected(self):
        self.seat_data["hands"][0]["seats"][1]["actor"] = "hero"
        self.save_seats()
        self.stack_data["source_seat_manifest_sha256"] = stackmod.sha256(self.seats)
        self.save_stack()
        self.rejected()

    def test_seat_amount_tamper_rejected_even_with_rehashed_stack(self):
        self.seat_data["hands"][0]["seats"][1]["net_contribution"] = "21"
        self.seat_data["hands"][0]["seats"][1]["stack_after_contribution"] = "79"
        self.save_seats()
        self.stack_data["source_seat_manifest_sha256"] = stackmod.sha256(self.seats)
        self.save_stack()
        self.rejected()

    def test_wrong_recording_identity_rejected(self):
        self.stack_data["recording_sha256"] = "b" * 64
        self.save_stack()
        self.rejected()

    def test_duplicate_json_key_rejected(self):
        self.review.write_text(self.review.read_text().replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,', 1))
        self.rejected()

    def test_invalid_json_nan_rejected(self):
        self.stack.write_text(self.stack.read_text().replace('"schema_version": 1,', '"schema_version": NaN,', 1))
        self.rejected()

    def test_missing_seat_action_actor_rejected(self):
        self.seat_data["hands"][0]["seats"][0]["actor"] = "seat_3"
        self.save_seats()
        self.stack_data["source_seat_manifest_sha256"] = stackmod.sha256(self.seats)
        self.save_stack()
        self.rejected()

    def test_output_contains_only_derived_provenance_not_hidden_cards(self):
        data = self.run_audit()
        self.assertNotIn("opponent_hole_cards", json.dumps(data))
        self.assertNotIn("equity_result", json.dumps(data))
        self.assertFalse(data["complete_hand_reconstructed"])

    def test_bad_stack_hand_count_rejected(self):
        self.stack_data["hands"].pop()
        self.save_stack()
        self.rejected()

    def test_manifest_not_confirmed_rejected(self):
        self.seat_data["reviewer_confirmed_offline"] = False
        self.save_seats()
        self.stack_data["source_seat_manifest_sha256"] = stackmod.sha256(self.seats)
        self.save_stack()
        self.rejected()

    def test_unknown_seat_state_is_explicit(self):
        self.seat_data["hands"][0]["seats"][1]["state"] = "unknown"
        self.save_seats()
        self.stack.unlink()
        stackmod.audit(self.pot, self.seats, self.stack)
        self.assertIn("seat_state_unknown", self.run_audit()["hands"][0]["blockers"])

    def test_observed_all_in_conflict_is_flagged(self):
        self.seat_data["hands"][0]["seats"][0]["state"] = "active"
        self.review_data["hands"][0]["actions"][0]["action_label_as_observed"] = "all-in"
        self.review.write_text(json.dumps(self.review_data))
        self.pot_data["source_betting_review_sha256"] = stackmod.sha256(self.review)
        self.save_pot()
        self.seat_data["source_pot_audit_sha256"] = stackmod.sha256(self.pot)
        self.save_seats()
        self.stack.unlink()
        stackmod.audit(self.pot, self.seats, self.stack)
        h = self.run_audit()["hands"][0]
        self.assertIn("observed_all_in_label_disagrees_with_seat_state", h["blockers"])

    def test_cross_stage_observed_total_tampering_rejected(self):
        self.pot_data["hands"][0]["reviewed_action_contributions"] = "66.50"
        self.pot_data["hands"][0]["conditional_pot_estimate"] = "68.50"
        self.pot_data["hands"][0]["conditional_difference"] = "-51.50"
        self.save_pot()
        self.seat_data["source_pot_audit_sha256"] = stackmod.sha256(self.pot)
        self.save_seats()
        self.stack.unlink()
        stackmod.audit(self.pot, self.seats, self.stack)
        self.rejected()

    def test_output_input_alias_rejected(self):
        with self.assertRaises(ValueError):
            mod.audit(self.review, self.pot, self.seats, self.stack, self.review)

    def test_gap_threshold_float_is_recorded(self):
        self.assertEqual(self.run_audit(gap_seconds=2.5)["gap_threshold_seconds"], 2.5)

    def test_manual_manifest_never_certifies_equity(self):
        result = self.run_audit()
        self.assertTrue(all("opponent_ranges_not_verified" in h["blockers"] for h in result["hands"]))
        self.assertTrue(all(h["automatic_clip_selection_authorized"] is False for h in result["hands"]))

    def test_output_parent_must_exist(self):
        with self.assertRaises(ValueError):
            mod.audit(self.review, self.pot, self.seats, self.stack, self.root / "missing" / "out.json")


if __name__ == "__main__":
    unittest.main()
