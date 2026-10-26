"""Synthetic unit tests; no real hands, video or verified strategic outcomes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from offline_pot_limit_decision_bounds import assess, export, strict_json


def ledger(**changes):
    row = dict(schema_version=1, variant="PLO5", source="synthetic",
               pot_before_action=100, actor_contribution_street=10,
               highest_contribution_street=30, actor_stack_remaining=200,
               min_full_raise_increment=20,
               observed_action={"kind": "raise", "target_contribution_street": 100}, notes="")
    row.update(changes)
    return row


class PotLimitTests(unittest.TestCase):
    def test_raise_cap(self):
        r = assess(ledger())
        self.assertEqual((r["to_call"], r["pot_after_hypothetical_call"],
                          r["pot_limit_max_total_contribution_street"],
                          r["min_full_raise_total_contribution_street"]), (20, 120, 150, 50))
        self.assertFalse(r["review_flags"])
        self.assertFalse(r["betting_rules_verified"])

    def test_stack_capped(self):
        r = assess(ledger(actor_stack_remaining=80))
        self.assertEqual(r["pot_limit_max_total_contribution_street"], 90)

    def test_pot_cap_exceeded(self):
        r = assess(ledger(observed_action={"kind": "raise", "target_contribution_street": 151}))
        self.assertIn("target_exceeds_pot_limit_cap", r["review_flags"])

    def test_min_raise_violation(self):
        r = assess(ledger(observed_action={"kind": "raise", "target_contribution_street": 40}))
        self.assertIn("raise_below_declared_full_raise_minimum", r["review_flags"])

    def test_short_all_in(self):
        r = assess(ledger(actor_stack_remaining=25,
                          observed_action={"kind": "raise", "target_contribution_street": 35}))
        self.assertIn("short_all_in_raise_may_not_reopen_action", r["review_flags"])
        self.assertNotIn("raise_below_declared_full_raise_minimum", r["review_flags"])

    def test_no_raise_when_short_of_call(self):
        r = assess(ledger(actor_stack_remaining=15,
                          observed_action={"kind": "raise", "target_contribution_street": 25}))
        self.assertIn("no_stack_available_to_raise", r["review_flags"])

    def test_call_full(self):
        r = assess(ledger(observed_action={"kind": "call", "target_contribution_street": 30}))
        self.assertFalse(r["review_flags"])

    def test_call_short_all_in(self):
        r = assess(ledger(actor_stack_remaining=15,
                          observed_action={"kind": "call", "target_contribution_street": 25}))
        self.assertFalse(r["review_flags"])

    def test_call_wrong_target(self):
        r = assess(ledger(observed_action={"kind": "call", "target_contribution_street": 20}))
        self.assertIn("call_target_mismatch_including_short_all_in", r["review_flags"])

    def test_check_faces_call(self):
        self.assertIn("check_faces_call", assess(ledger(observed_action={"kind": "check", "target_contribution_street": None}))["review_flags"])

    def test_fold_allowed(self):
        self.assertFalse(assess(ledger(observed_action={"kind": "fold", "target_contribution_street": None}))["review_flags"])

    def test_open_bet(self):
        r = assess(ledger(actor_contribution_street=0, highest_contribution_street=0,
                          observed_action={"kind": "bet", "target_contribution_street": 100}))
        self.assertEqual(r["pot_limit_max_total_contribution_street"], 100)
        self.assertFalse(r["review_flags"])

    def test_open_bet_too_small(self):
        r = assess(ledger(actor_contribution_street=0, highest_contribution_street=0,
                          observed_action={"kind": "bet", "target_contribution_street": 10}))
        self.assertIn("opening_bet_below_declared_minimum", r["review_flags"])

    def test_missing_increment(self):
        r = assess(ledger(min_full_raise_increment=None))
        self.assertIn("min_raise_increment_unknown", r["review_flags"])
        self.assertIsNone(r["min_full_raise_total_contribution_street"])

    def test_plo6(self):
        self.assertEqual(assess(ledger(variant="PLO6"))["variant"], "PLO6")

    def test_invalid_inconsistent_pot(self):
        with self.assertRaises(ValueError):
            assess(ledger(pot_before_action=20))

    def test_bool_not_integer(self):
        with self.assertRaises(ValueError):
            assess(ledger(actor_stack_remaining=True))

    def test_negative_chips(self):
        with self.assertRaises(ValueError):
            assess(ledger(pot_before_action=-1))

    def test_overflow(self):
        with self.assertRaises(ValueError):
            assess(ledger(actor_stack_remaining=10**12))

    def test_unknown_key(self):
        with self.assertRaises(ValueError):
            assess(ledger(secret="bad"))

    def test_bad_action_target_semantics(self):
        with self.assertRaises(ValueError):
            assess(ledger(observed_action={"kind": "fold", "target_contribution_street": 30}))

    def test_bad_source(self):
        with self.assertRaises(ValueError):
            assess(ledger(source="video_verified"))

    def test_export_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "ledger.json", Path(tmp) / "report.json"
            a.write_text(json.dumps(ledger()), encoding="utf-8")
            result = export(a, b)
            self.assertEqual(result["status"], "conditional_pot_limit_arithmetic_not_video_verified")
            self.assertEqual(json.loads(b.read_text())["review_flags"], [])
            with self.assertRaises(ValueError):
                export(a, b)

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                strict_json(p)

    def test_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            q = Path(tmp) / "y.json"
            p.write_text(json.dumps(ledger()))
            q.symlink_to(p)
            with self.assertRaises(ValueError):
                strict_json(q)


if __name__ == "__main__":
    unittest.main()
