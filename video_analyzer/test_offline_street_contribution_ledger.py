"""Deterministic synthetic tests; no real video or verified poker history."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from offline_street_contribution_ledger import reconstruct, export


def event(street, actor, kind, delta=0, pts=0.0, confidence=1.0, inc=None):
    return {"street": street, "actor": actor, "kind": kind,
            "delta_chips": delta, "source_pts_seconds": pts,
            "confidence": confidence, "evidence": "synthetic",
            "min_full_raise_increment": inc}


def sample(variant="PLO5", table=1):
    return {"schema_version": 1, "variant": variant, "source": "synthetic",
            "table_id": table, "hand_label": "hand-001", "starting_pot": 0,
            "initial_stacks": {"hero": 200, "villain": 200},
            "events": [
                event("preflop", "hero", "post_blind", 5, 0.1),
                event("preflop", "villain", "post_blind", 10, 0.2),
                event("preflop", "hero", "call", 5, 0.3),
                event("preflop", "villain", "check", 0, 0.4),
                event("flop", "hero", "bet", 10, 0.5, inc=5),
                event("flop", "villain", "fold", 0, 0.6),
            ]}


class LedgerTests(unittest.TestCase):
    def test_conservation(self):
        r = reconstruct(sample())
        self.assertEqual(r["final_pot"], 30)
        self.assertEqual(r["final_stacks"], {"hero": 180, "villain": 190})
        self.assertTrue(r["chip_conservation_under_declared_events"])

    def test_street_reset(self):
        r = reconstruct(sample())
        self.assertEqual(r["events"][4]["actor_contribution_before_street"], 0)
        self.assertEqual(r["events"][4]["highest_contribution_before_street"], 0)
        self.assertEqual(r["events"][4]["pot_before_action"], 20)

    def test_call_delta_semantics(self):
        r = reconstruct(sample())
        self.assertEqual(r["events"][2]["actor_contribution_after_street"], 10)
        self.assertEqual(r["events"][2]["pot_limit_bounds_conditional"]["to_call"], 5)
        self.assertEqual(r["events"][2]["review_flags"], [])

    def test_pot_limit_ceiling(self):
        d = sample()
        d["events"][2] = event("preflop", "hero", "raise", 45, 0.3, inc=10)
        r = reconstruct(d)
        self.assertIn("target_exceeds_pot_limit_cap", r["events"][2]["review_flags"])
        self.assertFalse(r["betting_rules_verified"])

    def test_legal_raise_conditional(self):
        d = sample()
        d["events"] = d["events"][:2] + [event("preflop", "hero", "raise", 25, 0.3, inc=10)]
        r = reconstruct(d)
        self.assertEqual(r["events"][2]["pot_limit_bounds_conditional"]["pot_limit_max_total_contribution_street"], 30)
        self.assertEqual(r["events"][2]["review_flags"], [])

    def test_short_call_allin(self):
        d = sample()
        d["initial_stacks"]["hero"] = 7
        d["events"] = d["events"][:2] + [event("preflop", "hero", "call", 2, 0.3)]
        r = reconstruct(d)
        self.assertEqual(r["events"][2]["review_flags"], [])
        self.assertEqual(r["final_stacks"]["hero"], 0)

    def test_mismatch_call_flag(self):
        d = sample()
        d["events"] = d["events"][:2] + [event("preflop", "hero", "call", 4, 0.3)]
        self.assertIn("call_target_mismatch_including_short_all_in",
                      reconstruct(d)["events"][2]["review_flags"])

    def test_unknown_minimum_flag(self):
        d = sample()
        d["events"][4]["min_full_raise_increment"] = None
        self.assertIn("opening_minimum_bet_unknown", reconstruct(d)["events"][4]["review_flags"])

    def test_low_confidence(self):
        d = sample()
        d["events"][4]["confidence"] = 0.3
        self.assertIn("low_observation_confidence", reconstruct(d)["review_flags"])

    def test_no_blinds_warning(self):
        d = sample()
        d["events"] = []
        self.assertIn("preflop_blinds_not_explicit", reconstruct(d)["review_flags"])

    def test_four_tables_independent(self):
        for table in range(1, 5):
            d = sample("PLO6", table)
            r = reconstruct(d)
            self.assertEqual(r["table_id"], table)
            self.assertEqual(r["variant"], "PLO6")
            self.assertEqual(r["final_pot"], 30)

    def test_no_verification_gates(self):
        r = reconstruct(sample())
        for key in ("video_evidence_verified", "betting_rules_verified", "ready_for_equity_or_ev", "automatic_clip_selection_authorized"):
            self.assertIs(r[key], False)

    def test_determinism(self):
        self.assertEqual(reconstruct(sample()), reconstruct(sample()))

    def test_actor_unknown(self):
        d = sample()
        d["events"][0]["actor"] = "ghost"
        with self.assertRaises(ValueError): reconstruct(d)

    def test_negative_delta(self):
        d = sample()
        d["events"][2]["delta_chips"] = -1
        with self.assertRaises(ValueError): reconstruct(d)

    def test_bool_delta(self):
        d = sample()
        d["events"][2]["delta_chips"] = True
        with self.assertRaises(ValueError): reconstruct(d)

    def test_overstack(self):
        d = sample()
        d["events"][2]["delta_chips"] = 300
        with self.assertRaises(ValueError): reconstruct(d)

    def test_action_after_fold(self):
        d = sample()
        d["events"].append(event("turn", "villain", "check", 0, 0.7))
        with self.assertRaises(ValueError): reconstruct(d)

    def test_street_regression(self):
        d = sample()
        d["events"].append(event("preflop", "hero", "check", 0, 0.7))
        with self.assertRaises(ValueError): reconstruct(d)

    def test_time_regression(self):
        d = sample()
        d["events"][3]["source_pts_seconds"] = 0.1
        with self.assertRaises(ValueError): reconstruct(d)

    def test_nan_rejected(self):
        d = sample()
        d["events"][3]["confidence"] = float("nan")
        with self.assertRaises(ValueError): reconstruct(d)

    def test_bad_fold_delta(self):
        d = sample()
        d["events"][-1]["delta_chips"] = 1
        with self.assertRaises(ValueError): reconstruct(d)

    def test_blind_after_action(self):
        d = sample()
        d["events"].append(event("preflop", "hero", "post_blind", 1, 0.7))
        with self.assertRaises(ValueError): reconstruct(d)

    def test_export_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, out = Path(folder)/"in.json", Path(folder)/"out.json"
            inp.write_text(json.dumps(sample()), encoding="utf-8")
            self.assertEqual(export(inp, out)["final_pot"], 30)
            original = out.read_bytes()
            with self.assertRaises(ValueError): export(inp, out)
            self.assertEqual(out.read_bytes(), original)

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, out = Path(folder)/"in.json", Path(folder)/"out.json"
            inp.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ValueError): export(inp, out)
            self.assertFalse(out.exists())

    def test_source_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, out = Path(folder)/"in.json", Path(folder)/"out.json"
            raw = json.dumps(sample()).encode()
            inp.write_bytes(raw)
            export(inp, out)
            self.assertEqual(inp.read_bytes(), raw)

    def test_invalid_source(self):
        d = sample()
        d["source"] = "video_verified"
        with self.assertRaises(ValueError): reconstruct(d)

    def test_reject_unexpected_fields(self):
        d = sample()
        d["events"][0]["inferred_cards"] = ["As"]
        with self.assertRaises(ValueError): reconstruct(d)

    def test_initial_stacks_unchanged(self):
        d = sample()
        before = copy.deepcopy(d)
        reconstruct(d)
        self.assertEqual(d, before)


if __name__ == "__main__":
    unittest.main()
