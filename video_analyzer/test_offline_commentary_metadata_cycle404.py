"""Regression tests for conservative offline commentary eligibility."""
import unittest

from video_analyzer.offline_conditional_commentary_gate import assess_conditional_commentary


def hand():
    return {
        "table_id": "table-1", "hand_id": "hand-1",
        "video_sha256": "a" * 64, "variant": "PLO5",
        "hero_cards": ["Ac", "Kd", "Qh", "Js", "Tc"],
        "board_cards": ["2c", "3d", "4h"],
        "action": "call", "pot": 100, "call_cost": 20,
        "start_pts": 5, "end_pts": 15, "human_reviewed": True,
        "range_sources": ["tight", "loose"],
    }


def comparison():
    return {
        "status": "CONDITIONAL_ONLY",
        "cross_range_comparison_available": True,
        "hand_error_verified": False,
        "gto_solution": False,
        "stable_action": None,
        "range_sensitive_or_inconclusive": True,
    }


class TestCommentaryGateMetadata(unittest.TestCase):
    def test_valid_conditional_only(self):
        self.assertEqual(
            assess_conditional_commentary(hand(), comparison())["status"],
            "CONDITIONAL_EXPLANATION_ALLOWED",
        )

    def test_bad_identifiers_fail_closed(self):
        for key in ("table_id", "hand_id"):
            for value in ([], {}, 1, True, "   "):
                with self.subTest(key=key, value=value):
                    h = hand()
                    h[key] = value
                    result = assess_conditional_commentary(h, comparison())
                    self.assertEqual(result["status"], "REVIEW_ONLY")
                    self.assertIn("invalid_" + key, result["reasons"])

    def test_invalid_stable_action_fails_closed(self):
        for value in ([], {}, 1, "all-in", ""):
            with self.subTest(value=value):
                c = comparison()
                c["stable_action"] = value
                result = assess_conditional_commentary(hand(), c)
                self.assertEqual(result["status"], "REVIEW_ONLY")
                self.assertIn("invalid_stable_action", result["reasons"])

    def test_range_sensitivity_must_be_explicit_boolean(self):
        for value in (None, 0, 1, "false", []):
            with self.subTest(value=value):
                c = comparison()
                c["range_sensitive_or_inconclusive"] = value
                result = assess_conditional_commentary(hand(), c)
                self.assertEqual(result["status"], "REVIEW_ONLY")
                self.assertIn("invalid_range_sensitivity", result["reasons"])

    def test_false_sensitivity_stays_false(self):
        c = comparison()
        c["range_sensitive_or_inconclusive"] = False
        result = assess_conditional_commentary(hand(), c)
        self.assertEqual(result["status"], "CONDITIONAL_EXPLANATION_ALLOWED")
        self.assertIs(result["range_sensitive_or_inconclusive"], False)


if __name__ == "__main__":
    unittest.main()
