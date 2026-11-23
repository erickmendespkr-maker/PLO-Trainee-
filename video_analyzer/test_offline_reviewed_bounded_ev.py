"""End-to-end offline reviewed evidence -> bounded equity -> conditional EV tests.

Run: python -m unittest video_analyzer.test_offline_reviewed_bounded_ev
All evidence and showdown samples here are synthetic, not recorded hands.
"""
import unittest

from .offline_bounded_equity_scenarios import bounded_equity_scenario, to_call_scenario
from .offline_reviewed_call_report import build_reviewed_call_report


def evidence(**overrides):
    item = dict(video_sha256="a" * 64, hand_id="synthetic-hand-1",
                table_id=1, start_pts=10.0, end_pts=35.0,
                hole_cards_verified=True, board_verified=True,
                action_verified=True, pot_verified=True,
                call_cost_verified=True, reviewed_by_human=True)
    item.update(overrides)
    return item


def scenario(name, wins, losses, seed):
    shares = [1.0] * wins + [0.0] * losses
    return to_call_scenario(bounded_equity_scenario(
        name, shares, seed=seed, range_assumption="synthetic fixed range " + name))


class ReviewedBoundedEVTests(unittest.TestCase):
    def test_reviewed_positive_conditional_only(self):
        result = build_reviewed_call_report(
            evidence(), 100, 20, [scenario("wide", 800, 200, 11)])
        self.assertEqual(result["status"], "CONDITIONAL_MODEL_ONLY")
        self.assertEqual(result["strategic_verdict"], "NOT_ESTABLISHED")
        self.assertFalse(result["gto_solution"])
        self.assertEqual(result["analysis"]["classification"],
                         "POSITIVE_IN_ALL_SUPPLIED_SCENARIOS")
        self.assertFalse(result["analysis"]["scenario_envelope_is_confidence_interval"])

    def test_missing_review_blocks_ev(self):
        result = build_reviewed_call_report(
            evidence(reviewed_by_human=False), 100, 20,
            [scenario("wide", 800, 200, 11)])
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["analysis"])
        self.assertIn("reviewed_by_human", result["missing_fields"])

    def test_unverified_pot_blocks_ev(self):
        result = build_reviewed_call_report(
            evidence(pot_verified=False), 100, 20,
            [scenario("wide", 800, 200, 11)])
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIn("pot_verified", result["missing_fields"])

    def test_missing_video_identity_blocks_ev(self):
        item = evidence()
        del item["video_sha256"]
        result = build_reviewed_call_report(
            item, 100, 20, [scenario("wide", 800, 200, 11)])
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIn("video_sha256", result["missing_fields"])

    def test_opposing_ranges_remain_sensitive(self):
        result = build_reviewed_call_report(
            evidence(), 100, 50,
            [scenario("wide", 800, 200, 11),
             scenario("tight", 200, 800, 12)])
        self.assertEqual(result["analysis"]["classification"],
                         "RANGE_OR_SAMPLING_SENSITIVE")
        self.assertEqual(result["strategic_verdict"], "NOT_ESTABLISHED")

    def test_low_sample_precision_cannot_be_promoted(self):
        summary = bounded_equity_scenario(
            "uncertain", [1.0] * 15 + [0.0] * 15,
            seed=17, range_assumption="synthetic")
        self.assertEqual(summary["status"], "INSUFFICIENT_PRECISION")
        with self.assertRaises(ValueError):
            to_call_scenario(summary)

    def test_reproducible_conditional_report(self):
        a = build_reviewed_call_report(
            evidence(), 100, 20, [scenario("wide", 800, 200, 11)])
        b = build_reviewed_call_report(
            evidence(), 100, 20, [scenario("wide", 800, 200, 11)])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
