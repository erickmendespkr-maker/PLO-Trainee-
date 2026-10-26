"""Synthetic tests; no claims of source-video accuracy or betting legality."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_betting_action_triage import audit_snapshot, digest, export_audit


def action(street, actor, kind, amount, pts):
    return {"street": street, "actor": actor, "action": kind,
            "amount": amount, "source_pts_seconds": pts}


def fixture():
    entry = {"variant": "PLO5", "table_id": 1, "hand_label_human_assigned": "h1",
             "hero_cards": ["As", "Kh", "Qd", "Jc", "Tc"],
             "board_by_street": {"flop": ["2h", "3d", "4c"], "turn": "5s", "river": "6h"},
             "source_pts_start_seconds": 1, "source_pts_end_seconds": 9,
             "actions": [action("preflop", "villain_1", "bet", 5, 2),
                         action("preflop", "hero", "call", 5, 3),
                         action("flop", "hero", "check", 0, 5)],
             "pot_before_decision": 10, "call_amount": 5, "effective_stack": 100,
             "opponent_range_notes": "Synthetic scenario only", "notes": "",
             "confidence_subjective": .6}
    row = {"table_id": 1, "hand_label_human_assigned": "h1",
           "human_entry_candidate": entry,
           "candidate_human_entry_sha256": digest(entry),
           "hand_reconstruction_verified": False, "source_pts_verified": False,
           "ready_for_equity_or_ev": False,
           "automatic_clip_selection_authorized": False}
    return {"schema_version": 1,
            "status": "derived_human_reviewed_snapshot_not_video_verified",
            "job_id": "a"*32, "source_recording_sha256": "b"*64,
            "hands": [row],
            "hand_reconstruction_verified": False, "source_pts_verified": False,
            "ready_for_equity_or_ev": False,
            "automatic_clip_selection_authorized": False}


def rehash(snap):
    for row in snap["hands"]:
        row["candidate_human_entry_sha256"] = digest(row["human_entry_candidate"])
    return snap


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.snap = fixture()

    def result(self):
        return audit_snapshot(rehash(self.snap))

    def test_clean_trace_has_no_flags(self):
        self.assertEqual(self.result()["counts"]["hands_with_flags"], 0)

    def test_no_math_or_clips(self):
        result = self.result()
        self.assertFalse(result["betting_rules_verified"])
        self.assertFalse(result["ready_for_equity_or_ev"])
        self.assertFalse(result["automatic_clip_selection_authorized"])

    def test_missing_interval(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["source_pts_start_seconds"] = e["source_pts_end_seconds"] = None
        self.assertIn("hand_interval_missing", self.result()["hands"][0]["review_flags"])

    def test_missing_hero(self):
        self.snap["hands"][0]["human_entry_candidate"]["hero_cards"] = None
        self.assertIn("hero_cards_missing", self.result()["hands"][0]["review_flags"])

    def test_missing_flop(self):
        self.snap["hands"][0]["human_entry_candidate"]["board_by_street"]["flop"] = None
        self.assertIn("flop_not_visible", self.result()["hands"][0]["review_flags"])

    def test_unknown_actor(self):
        self.snap["hands"][0]["human_entry_candidate"]["actions"][0]["actor"] = "unknown"
        self.assertIn("actor_unknown", self.result()["hands"][0]["review_flags"])

    def test_fold_then_action(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["actions"] = [action("preflop", "hero", "fold", 0, 2),
                        action("preflop", "hero", "bet", 10, 3)]
        self.assertIn("action_after_visible_fold", self.result()["hands"][0]["review_flags"])

    def test_consecutive_same_actor(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["actions"] = [action("preflop", "hero", "bet", 3, 2),
                        action("preflop", "hero", "raise", 6, 3)]
        self.assertIn("consecutive_actions_same_actor", self.result()["hands"][0]["review_flags"])

    def test_same_pts(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["actions"][1]["source_pts_seconds"] = 2
        self.assertIn("same_pts_multiple_actions", self.result()["hands"][0]["review_flags"])

    def test_bet_after_raise(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["actions"] = [action("flop", "hero", "raise", 15, 5),
                        action("flop", "villain_1", "bet", 10, 6)]
        self.assertIn("bet_after_aggressive_action_check_labels", self.result()["hands"][0]["review_flags"])

    def test_call_without_prior_visible_action(self):
        self.snap["hands"][0]["human_entry_candidate"]["actions"] = [action("preflop", "hero", "call", 3, 2)]
        self.assertIn("call_or_raise_without_visible_prior_action", self.result()["hands"][0]["review_flags"])

    def test_missing_pot_call_stack_and_range(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e.update({"pot_before_decision": None, "call_amount": None,
                  "effective_stack": None, "opponent_range_notes": ""})
        flags = self.result()["hands"][0]["review_flags"]
        for key in ("pot_before_decision_missing", "call_amount_missing",
                    "effective_stack_missing", "opponent_range_unspecified"):
            self.assertIn(key, flags)

    def test_empty_actions(self):
        self.snap["hands"][0]["human_entry_candidate"]["actions"] = []
        self.assertIn("actions_missing", self.result()["hands"][0]["review_flags"])

    def test_four_tables_no_cross_table_overlap(self):
        base = self.snap["hands"][0]
        for table in (2, 3, 4):
            row = copy.deepcopy(base)
            row["table_id"] = row["human_entry_candidate"]["table_id"] = table
            self.snap["hands"].append(row)
        self.assertEqual(self.result()["counts"]["hands"], 4)
        self.assertEqual(self.result()["counts"]["hands_with_flags"], 0)

    def test_same_table_overlap(self):
        row = copy.deepcopy(self.snap["hands"][0])
        row["hand_label_human_assigned"] = row["human_entry_candidate"]["hand_label_human_assigned"] = "h2"
        row["human_entry_candidate"]["source_pts_start_seconds"] = 5
        row["human_entry_candidate"]["source_pts_end_seconds"] = 12
        row["human_entry_candidate"]["actions"] = []
        self.snap["hands"].append(row)
        self.assertIn("overlap_with_prior_hand_same_table", self.result()["hands"][1]["review_flags"])

    def test_touching_intervals_not_overlap(self):
        row = copy.deepcopy(self.snap["hands"][0])
        row["hand_label_human_assigned"] = row["human_entry_candidate"]["hand_label_human_assigned"] = "h2"
        row["human_entry_candidate"]["source_pts_start_seconds"] = 9
        row["human_entry_candidate"]["source_pts_end_seconds"] = 12
        row["human_entry_candidate"]["actions"] = []
        self.snap["hands"].append(row)
        self.assertNotIn("overlap_with_prior_hand_same_table", self.result()["hands"][1]["review_flags"])

    def test_reject_candidate_hash_mismatch(self):
        self.snap["hands"][0]["human_entry_candidate"]["notes"] = "changed"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            audit_snapshot(self.snap)

    def test_reject_gate_escalation(self):
        self.snap["ready_for_equity_or_ev"] = True
        with self.assertRaisesRegex(ValueError, "asserts verification"):
            self.result()

    def test_reject_row_gate_escalation(self):
        self.snap["hands"][0]["automatic_clip_selection_authorized"] = True
        with self.assertRaisesRegex(ValueError, "asserts verification"):
            self.result()

    def test_reject_bad_pts(self):
        self.snap["hands"][0]["human_entry_candidate"]["actions"][1]["source_pts_seconds"] = 1
        with self.assertRaisesRegex(ValueError, "nonchronological"):
            self.result()

    def test_reject_duplicate_identity(self):
        self.snap["hands"].append(copy.deepcopy(self.snap["hands"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.result()

    def test_reject_wrong_variant_count(self):
        self.snap["hands"][0]["human_entry_candidate"]["variant"] = "PLO6"
        with self.assertRaisesRegex(ValueError, "Wrong hero"):
            self.result()

    def test_deterministic(self):
        self.assertEqual(self.result(), self.result())

    def test_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp)/"snapshot.json", Path(tmp)/"report.json"
            inp.write_text(json.dumps(self.snap))
            export_audit(inp, out)
            self.assertEqual(json.loads(out.read_text())["counts"]["hands"], 1)
            with self.assertRaisesRegex(ValueError, "Unsafe output"):
                export_audit(inp, out)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, alias, out = (Path(tmp)/x for x in ("snapshot.json", "alias.json", "report.json"))
            inp.write_text(json.dumps(self.snap))
            alias.symlink_to(inp)
            with self.assertRaisesRegex(ValueError, "Unsafe snapshot"):
                export_audit(alias, out)

    def test_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp)/"snapshot.json", Path(tmp)/"report.json"
            inp.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                export_audit(inp, out)

    def test_reject_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp)/"snapshot.json", Path(tmp)/"report.json"
            inp.write_text('{"schema_version":NaN}')
            with self.assertRaises(ValueError):
                export_audit(inp, out)

    def test_reject_reversed_hand_interval(self):
        e = self.snap["hands"][0]["human_entry_candidate"]
        e["source_pts_start_seconds"] = 9
        e["source_pts_end_seconds"] = 1
        with self.assertRaisesRegex(ValueError, "Invalid source interval"):
            self.result()

    def test_snapshot_not_modified(self):
        before = copy.deepcopy(self.snap)
        self.result()
        self.assertEqual(self.snap, before)


if __name__ == "__main__":
    unittest.main()
