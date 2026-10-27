"""Synthetic, offline tests. No poker integration or live play."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import offline_four_table_stack_sidepot_audit as mod

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cycle153_pot_gap_report_input.json"


def manifest_for(source, source_path):
    hands = []
    for h in source["hands"]:
        total = sum((mod.chips(h[f]) for f in ("reviewed_action_contributions",
                     "manual_forced_contributions", "manual_unobserved_contributions")), mod.Decimal(0)) - \
                mod.chips(h["manual_returned_uncalled_bets"])
        hands.append({"hand_id": h["hand_id"], "table_id": h["table_id"],
                      "seat_count": 2, "reviewer_notes": "Synthetic only, no visual evidence",
                      "seats": [{"actor": "hero", "starting_stack": "500", "net_contribution": str(total),
                                 "stack_after_contribution": str(mod.Decimal(500) - total),
                                 "state": "active", "reviewer_note": "Synthetic actor"},
                                {"actor": "seat_1", "starting_stack": "100", "net_contribution": "0",
                                 "stack_after_contribution": "100", "state": "active",
                                 "reviewer_note": "Synthetic actor"}]})
    return {"schema_version": 1, "source_pot_audit_sha256": mod.sha256(source_path),
            "reviewer_confirmed_offline": True, "hands": hands}


class StackSidepotAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.source = self.dir / "pot.json"
        self.source.write_bytes(FIXTURE.read_bytes())
        self.data = json.loads(self.source.read_text())
        self.manifest = manifest_for(self.data, self.source)
        self.manual = self.dir / "manual.json"
        self.save()
        self.output = self.dir / "result.json"

    def save(self):
        self.manual.write_text(json.dumps(self.manifest))

    def run_audit(self):
        return mod.audit(self.source, self.manual, self.output)

    def rejected(self):
        self.save()
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertFalse(self.output.exists())

    def test_four_tables_are_blocked(self):
        out = self.run_audit()
        self.assertEqual(len(out["hands"]), 4)
        self.assertFalse(out["ready_for_equity_or_ev"])
        self.assertFalse(out["automatic_clip_selection_authorized"])
        self.assertFalse(out["complete_hand_reconstructed"])
        self.assertTrue(all(not h["side_pot_eligibility_verified"] for h in out["hands"]))

    def test_source_sha_bound(self):
        self.assertEqual(self.run_audit()["source_pot_audit_sha256"], mod.sha256(self.source))

    def test_manifest_sha_bound(self):
        self.assertEqual(self.run_audit()["source_seat_manifest_sha256"], mod.sha256(self.manual))

    def test_seat_totals_match_conditional(self):
        h = self.run_audit()["hands"][0]
        self.assertEqual(h["net_pot_audit_contributions"], "67.50")
        self.assertEqual(h["conditional_contribution_difference"], "0.00")

    def test_single_contributor_top_flag(self):
        self.assertIn("single_contributor_top_layer_requires_refund_review", self.run_audit()["hands"][0]["blockers"])

    def test_source_pot_discrepancy_propagated(self):
        self.assertIn("conditional_pot_discrepancy", self.run_audit()["hands"][0]["blockers"])

    def test_template_unconfirmed(self):
        template = mod.make_template(self.source, self.dir / "template.json")
        self.assertFalse(template["reviewer_confirmed_offline"])
        self.assertEqual(len(template["hands"]), 4)
        self.assertEqual(template["hands"][0]["seats"], [])

    def test_unconfirmed_rejected(self):
        self.manifest["reviewer_confirmed_offline"] = False
        self.rejected()

    def test_tampered_source_rejected(self):
        self.data["warning"] += " "
        self.source.write_text(json.dumps(self.data))
        self.rejected()

    def test_wrong_hand_id_rejected(self):
        self.manifest["hands"][0]["hand_id"] = "changed"
        self.rejected()

    def test_wrong_table_rejected(self):
        self.manifest["hands"][0]["table_id"] = 2
        self.rejected()

    def test_missing_seat_rejected(self):
        self.manifest["hands"][0]["seats"].pop()
        self.rejected()

    def test_duplicate_actor_rejected(self):
        self.manifest["hands"][0]["seats"][1]["actor"] = "hero"
        self.rejected()

    def test_unknown_actor_rejected(self):
        self.manifest["hands"][0]["seats"][1]["actor"] = "seat_3"
        self.rejected()

    def test_invalid_chip_rejected(self):
        self.manifest["hands"][0]["seats"][0]["net_contribution"] = "1e9"
        self.rejected()

    def test_float_chip_rejected(self):
        self.manifest["hands"][0]["seats"][0]["net_contribution"] = 2.0
        self.rejected()

    def test_negative_chip_rejected(self):
        self.manifest["hands"][0]["seats"][0]["net_contribution"] = "-1"
        self.rejected()

    def test_contribution_over_stack_rejected(self):
        self.manifest["hands"][0]["seats"][0]["starting_stack"] = "2"
        self.rejected()

    def test_stack_balance_rejected(self):
        self.manifest["hands"][0]["seats"][0]["stack_after_contribution"] = "499"
        self.rejected()

    def test_false_all_in_rejected(self):
        self.manifest["hands"][0]["seats"][0]["state"] = "all_in"
        self.rejected()

    def test_all_in_zero_remaining_accepted(self):
        hero = self.manifest["hands"][0]["seats"][0]
        hero["starting_stack"] = hero["net_contribution"]
        hero["stack_after_contribution"] = "0"
        hero["state"] = "all_in"
        self.save()
        self.assertEqual(self.run_audit()["hands"][0]["side_pot_tiers_conditional"][0]["eligible_if_states_correct"], ["hero"])

    def test_folded_actor_not_eligible(self):
        self.manifest["hands"][0]["seats"][0]["state"] = "folded"
        self.save()
        h = self.run_audit()["hands"][0]
        self.assertIn("no_eligible_contender_in_layer", h["blockers"])

    def test_unknown_state_flagged(self):
        self.manifest["hands"][0]["seats"][0]["state"] = "unknown"
        self.save()
        self.assertIn("layer_eligibility_uncertain", self.run_audit()["hands"][0]["blockers"])

    def test_null_preaward_stack_flagged(self):
        self.manifest["hands"][0]["seats"][0]["stack_after_contribution"] = None
        self.save()
        self.assertIn("pre_award_stack_unverified", self.run_audit()["hands"][0]["blockers"])

    def test_totals_mismatch_flagged_not_promoted(self):
        self.manifest["hands"][0]["seats"][0]["net_contribution"] = "60"
        self.manifest["hands"][0]["seats"][0]["stack_after_contribution"] = "440"
        self.save()
        h = self.run_audit()["hands"][0]
        self.assertIn("seat_total_vs_pot_audit_mismatch", h["blockers"])
        self.assertFalse(h["ready_for_equity_or_ev"])

    def test_side_pot_three_way_layers(self):
        s = [{"actor": "hero", "committed": mod.Decimal(40), "state": "all_in"},
             {"actor": "seat_1", "committed": mod.Decimal(80), "state": "all_in"},
             {"actor": "seat_2", "committed": mod.Decimal(100), "state": "active"}]
        tiers = mod.side_pot_tiers(s)
        self.assertEqual([t["amount"] for t in tiers], ["120", "80", "20"])
        self.assertEqual(tiers[1]["eligible_if_states_correct"], ["seat_1", "seat_2"])
        self.assertEqual(tiers[2]["contributors"], ["seat_2"])

    def test_folded_money_still_in_pot(self):
        s = [{"actor": "hero", "committed": mod.Decimal(20), "state": "folded"},
             {"actor": "seat_1", "committed": mod.Decimal(20), "state": "active"}]
        tiers = mod.side_pot_tiers(s)
        self.assertEqual(tiers[0]["amount"], "40")
        self.assertEqual(tiers[0]["eligible_if_states_correct"], ["seat_1"])

    def test_zero_contributors_no_tiers(self):
        self.assertEqual(mod.side_pot_tiers([{"actor": "hero", "committed": mod.Decimal(0), "state": "active"}]), [])

    def test_extra_fields_rejected(self):
        self.manifest["hands"][0]["seats"][0]["magic"] = True
        self.rejected()

    def test_missing_note_rejected(self):
        self.manifest["hands"][0]["reviewer_notes"] = ""
        self.rejected()

    def test_output_existing_not_overwritten(self):
        self.output.write_text("keep")
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertEqual(self.output.read_text(), "keep")

    def test_symlink_input_rejected(self):
        link = self.dir / "link.json"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            mod.audit(link, self.manual, self.output)

    def test_symlink_output_rejected(self):
        self.output.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_recording_hash_mismatch_rejected(self):
        rec = self.dir / "video.mp4"
        rec.write_bytes(b"fake synthetic recording")
        with self.assertRaises(ValueError):
            mod.audit(self.source, self.manual, self.output, recording_path=rec)

    def test_recording_hash_matches(self):
        rec = self.dir / "video.mp4"
        rec.write_bytes(b"fake synthetic recording")
        self.data["recording_sha256"] = hashlib.sha256(rec.read_bytes()).hexdigest()
        self.source.write_text(json.dumps(self.data))
        self.manifest["source_pot_audit_sha256"] = mod.sha256(self.source)
        self.save()
        self.assertTrue(mod.audit(self.source, self.manual, self.output, recording_path=rec)["recording_hash_checked_in_this_run"])

    def test_source_duplicate_json_keys_rejected(self):
        self.source.write_text('{"schema_version":1,"schema_version":1}')
        self.manifest["source_pot_audit_sha256"] = mod.sha256(self.source)
        self.rejected()

    def test_manual_duplicate_json_keys_rejected(self):
        self.manual.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_nan_rejected(self):
        self.manual.write_text('{"schema_version":NaN}')
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_bad_source_status_rejected(self):
        self.data["ready_for_equity_or_ev"] = True
        self.source.write_text(json.dumps(self.data))
        self.manifest["source_pot_audit_sha256"] = mod.sha256(self.source)
        self.rejected()

    def test_source_difference_inconsistent_rejected(self):
        self.data["hands"][0]["conditional_difference"] = "0"
        self.source.write_text(json.dumps(self.data))
        self.manifest["source_pot_audit_sha256"] = mod.sha256(self.source)
        self.rejected()

    def test_nonfinite_source_rejected(self):
        self.data["hands"][0]["conditional_difference"] = "NaN"
        self.source.write_text(json.dumps(self.data))
        self.manifest["source_pot_audit_sha256"] = mod.sha256(self.source)
        self.rejected()

    def test_no_file_write_on_missing_manifest(self):
        self.manual.unlink()
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
