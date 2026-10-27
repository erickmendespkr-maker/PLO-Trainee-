"""Synthetic-only tests for conservative conditional EV reporting."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline_reviewed_call_ev import evaluate, export


def fixture(variant="PLO5"):
    return {
        "schema_version": 1, "variant": variant, "table_id": 2,
        "hand_label": "synthetic-hand-01", "source_recording_sha256_claim": "a" * 64,
        "annotation_source": "synthetic",
        "hero_cards": ["Ac", "Kd", "Qh", "Js", "Tc"] + (["9d"] if variant == "PLO6" else []),
        "board_cards": ["2c", "3d", "4h"],
        "opponent_range": {"label": "synthetic_uniform", "opponents": 1,
                           "assumptions": ["Illustrative range only, not inferred from video"]},
        "equity_estimate": {"method": "external_monte_carlo", "equity": 0.4,
                            "ci_low": 0.38, "ci_high": 0.42, "trials": 10000,
                            "seed": 7, "ties_included": True,
                            "ci_label": "claimed_95_percent"},
        "decision": {"action": "call", "pot_before_call": 100,
                     "call_cost": 40, "remaining_stack": 100,
                     "expected_rake": 0, "no_future_betting": True,
                     "no_side_pots": True},
        "unresolved_fields": [],
    }


class ConditionalEVTests(unittest.TestCase):
    def test_positive_call(self):
        r = evaluate(fixture())
        self.assertTrue(r["conditional_ev_available"])
        self.assertEqual(r["ev_call_chips"], 16)
        self.assertEqual(r["ev_call_interval_chips"], [13.2, 18.8])
        self.assertEqual(r["ev_fold_chips"], 0)
        self.assertEqual(r["interval_interpretation"], "positive_across_claimed_interval")

    def test_plo6(self):
        self.assertTrue(evaluate(fixture("PLO6"))["conditional_ev_available"])

    def test_rake(self):
        d = fixture(); d["decision"]["expected_rake"] = 5
        self.assertEqual(evaluate(d)["ev_call_chips"], 11)

    def test_negative_interval(self):
        d = fixture(); d["equity_estimate"].update(equity=.1, ci_low=.09, ci_high=.11)
        self.assertEqual(evaluate(d)["interval_interpretation"], "negative_across_claimed_interval")

    def test_crossing_interval(self):
        d = fixture(); d["equity_estimate"].update(equity=.29, ci_low=.27, ci_high=.31)
        self.assertEqual(evaluate(d)["interval_interpretation"], "crosses_or_touches_zero")

    def test_missing_equity_blocks(self):
        d = fixture(); d["equity_estimate"] = None
        r = evaluate(d)
        self.assertFalse(r["conditional_ev_available"])
        self.assertIsNone(r["ev_call_chips"])

    def test_unresolved_blocks(self):
        d = fixture(); d["unresolved_fields"] = ["pot unreadable"]
        self.assertIn("unresolved_annotations", evaluate(d)["blocked_reasons"])

    def test_multiway_blocks(self):
        d = fixture(); d["opponent_range"]["opponents"] = 3
        self.assertFalse(evaluate(d)["conditional_ev_available"])

    def test_future_betting_blocks(self):
        d = fixture(); d["decision"]["no_future_betting"] = False
        self.assertFalse(evaluate(d)["conditional_ev_available"])

    def test_side_pots_block(self):
        d = fixture(); d["decision"]["no_side_pots"] = False
        self.assertFalse(evaluate(d)["conditional_ev_available"])

    def test_raise_blocks(self):
        d = fixture(); d["decision"]["action"] = "raise"
        self.assertFalse(evaluate(d)["conditional_ev_available"])

    def test_unaffordable_call_blocks(self):
        d = fixture(); d["decision"]["remaining_stack"] = 20
        self.assertFalse(evaluate(d)["conditional_ev_available"])

    def test_wrong_hero_count_rejected(self):
        d = fixture(); d["hero_cards"].pop()
        with self.assertRaises(ValueError): evaluate(d)

    def test_duplicate_card_rejected(self):
        d = fixture(); d["board_cards"][0] = "Ac"
        with self.assertRaises(ValueError): evaluate(d)

    def test_bad_board_count_rejected(self):
        d = fixture(); d["board_cards"] = ["2c", "3d"]
        with self.assertRaises(ValueError): evaluate(d)

    def test_bool_as_amount_rejected(self):
        d = fixture(); d["decision"]["call_cost"] = True
        with self.assertRaises(ValueError): evaluate(d)

    def test_nan_rejected(self):
        d = fixture(); d["equity_estimate"]["equity"] = float("nan")
        with self.assertRaises(ValueError): evaluate(d)

    def test_invalid_confidence_interval(self):
        d = fixture(); d["equity_estimate"]["ci_low"] = .5
        with self.assertRaises(ValueError): evaluate(d)

    def test_bad_seed(self):
        d = fixture(); d["equity_estimate"]["seed"] = -1
        with self.assertRaises(ValueError): evaluate(d)

    def test_no_overclaim(self):
        r = evaluate(fixture())
        self.assertFalse(r["video_evidence_verified"])
        self.assertFalse(r["monte_carlo_recomputed"])
        self.assertFalse(r["strategic_error_proven"])
        self.assertFalse(r["automatic_clip_selection_authorized"])

    def test_export_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root)/"input.json", Path(root)/"report.json"
            a.write_text(json.dumps(fixture()), encoding="utf-8")
            r = export(a, b)
            self.assertEqual(json.loads(b.read_text())["ev_call_chips"], r["ev_call_chips"])
            with self.assertRaises(ValueError): export(a, b)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root)/"input.json", Path(root)/"report.json"
            a.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(ValueError): export(a, b)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a, link, b = (Path(root)/n for n in ("input.json", "link.json", "out.json"))
            a.write_text(json.dumps(fixture()), encoding="utf-8")
            link.symlink_to(a)
            with self.assertRaises(ValueError): export(link, b)

    def test_extra_field_rejected(self):
        d = fixture(); d["automatic_clip_selection_authorized"] = True
        with self.assertRaises(ValueError): evaluate(d)

    def test_zero_call_blocks(self):
        d = fixture(); d["decision"]["call_cost"] = 0
        self.assertFalse(evaluate(d)["conditional_ev_available"])


if __name__ == "__main__":
    unittest.main()
