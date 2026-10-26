"""Synthetic regression tests for offline second-review decisions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_hand_correction_overlay import build_overlay, digest
from offline_hand_independent_review import build_review, export_review
from test_offline_hand_correction_overlay import fixture


def case():
    draft, submission = fixture()
    overlay = build_overlay(draft, submission)
    decisions = {"schema_version": 1, "job_id": draft["job_id"],
                 "source_draft_sha256": digest(draft), "overlay_sha256": digest(overlay),
                 "reviewer_label": "segundo revisor",
                 "decisions": [{"correction_sha256": digest(overlay["corrections"][0]),
                                "decision": "accept", "reason": "Revisei as evidências"}]}
    return draft, overlay, decisions


class IndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.draft, self.overlay, self.decisions = case()

    def run_review(self):
        return build_review(self.draft, self.overlay, self.decisions)

    def test_accept_does_not_authorize_math_or_mutate(self):
        original = copy.deepcopy(self.draft)
        result = self.run_review()
        self.assertEqual(result["counts"], {"accepted": 1, "rejected": 0})
        self.assertFalse(result["ready_for_equity_or_ev"])
        self.assertFalse(result["automatic_clip_selection_authorized"])
        self.assertEqual(original, self.draft)

    def test_rejection(self):
        self.decisions["decisions"][0]["decision"] = "reject"
        self.assertEqual(self.run_review()["counts"]["rejected"], 1)

    def test_same_reviewer(self):
        self.decisions["reviewer_label"] = "ANALISTA"
        with self.assertRaisesRegex(ValueError, "Independent"):
            self.run_review()

    def test_wrong_draft_hash(self):
        self.decisions["source_draft_sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.run_review()

    def test_wrong_overlay_hash(self):
        self.decisions["overlay_sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.run_review()

    def test_tampered_original_value(self):
        self.overlay["corrections"][0]["original_value"] = "fake"
        self.decisions["overlay_sha256"] = digest(self.overlay)
        with self.assertRaisesRegex(ValueError, "Altered"):
            self.run_review()

    def test_tampered_proposal(self):
        self.overlay["corrections"][0]["proposed_value"] = ["Ac", "Kh", "Qd", "Jc", "Tc"]
        self.decisions["overlay_sha256"] = digest(self.overlay)
        with self.assertRaisesRegex(ValueError, "Unknown or repeated"):
            self.run_review()

    def test_missing_decision(self):
        self.decisions["decisions"] = []
        with self.assertRaises(ValueError): self.run_review()

    def test_duplicate_decision(self):
        self.decisions["decisions"].append(copy.deepcopy(self.decisions["decisions"][0]))
        with self.assertRaises(ValueError): self.run_review()

    def test_unknown_decision_hash(self):
        self.decisions["decisions"][0]["correction_sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.run_review()

    def test_invalid_decision(self):
        self.decisions["decisions"][0]["decision"] = "approve_math"
        with self.assertRaises(ValueError): self.run_review()

    def test_empty_reason(self):
        self.decisions["decisions"][0]["reason"] = " "
        with self.assertRaises(ValueError): self.run_review()

    def test_conflicting_cards(self):
        self._second("board_by_street", {"flop": ["As", "2h", "3c"],
                                         "turn": None, "river": None})
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.run_review()

    def test_cross_field_pts_interval(self):
        self._second("source_pts_start_seconds", 12)
        self._second("source_pts_end_seconds", 10)
        with self.assertRaisesRegex(ValueError, "interval"):
            self.run_review()

    def test_reject_conflicting_proposal_does_not_block(self):
        self._second("board_by_street", {"flop": ["As", "2h", "3c"],
                                         "turn": None, "river": None})
        self.decisions["decisions"][-1]["decision"] = "reject"
        self.assertEqual(self.run_review()["counts"], {"accepted": 1, "rejected": 1})

    def test_action_outside_hand(self):
        self._second("source_pts_start_seconds", 10)
        self._second("actions", [{"street": "flop", "actor": "hero", "action": "call",
                                  "amount": 2, "source_pts_seconds": 5}])
        with self.assertRaisesRegex(ValueError, "before hand"):
            self.run_review()

    def test_call_exceeds_stack(self):
        self._second("call_amount", 100)
        self._second("effective_stack", 50)
        with self.assertRaisesRegex(ValueError, "stack"):
            self.run_review()

    def test_export_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b, c, out = [root / name for name in ("draft.json", "overlay.json", "review.json", "result.json")]
            for path, data in zip((a,b,c), (self.draft, self.overlay, self.decisions)):
                path.write_text(json.dumps(data))
            self.assertEqual(export_review(a,b,c,out)["counts"]["accepted"], 1)
            self.assertFalse(json.loads(out.read_text())["source_pts_verified"])
            with self.assertRaises(ValueError): export_review(a,b,c,out)

    def test_export_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b, c, out = [root / name for name in ("draft.json", "overlay.json", "review.json", "result.json")]
            for path, data in zip((a,b,c), (self.draft, self.overlay, self.decisions)):
                path.write_text(json.dumps(data))
            link = root / "link.json"
            link.symlink_to(a)
            with self.assertRaises(ValueError): export_review(link,b,c,out)

    def _second(self, field, value):
        original = self.draft["hands"][0]["human_entry"][field]
        sub = {"schema_version": 1, "job_id": self.draft["job_id"],
               "source_draft_sha256": digest(self.draft), "reviewer_label": "analista",
               "corrections": [{"table_id": 1, "hand_label_human_assigned": "h1",
                                "field": field, "expected_value_sha256": digest(original),
                                "proposed_value": value, "reason": "Manual", "confidence_subjective": .8}]}
        new_row = build_overlay(self.draft, sub)["corrections"][0]
        self.overlay["corrections"].append(new_row)
        self.overlay["corrections"].sort(key=lambda e: (e["table_id"],e["hand_label_human_assigned"],e["field"]))
        self.overlay["counts"]["pending"] += 1
        self.decisions["overlay_sha256"] = digest(self.overlay)
        self.decisions["decisions"].append({"correction_sha256": digest(new_row),
                                             "decision": "accept", "reason": "Revisado"})


if __name__ == "__main__":
    unittest.main()
