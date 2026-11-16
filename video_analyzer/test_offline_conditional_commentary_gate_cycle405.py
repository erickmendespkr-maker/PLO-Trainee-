"""Regression cases for conditional commentary evidence and scenario consistency."""
import unittest

try:
    from video_analyzer.offline_conditional_commentary_gate import assess_conditional_commentary
except ImportError:
    from offline_conditional_commentary_gate import assess_conditional_commentary


def valid_hand():
    return {
        "table_id": "table-1", "hand_id": "hand-1",
        "video_sha256": "a" * 64, "hero_cards": ["Ac", "Kd", "Qh", "Js", "Tc"],
        "board_cards": ["2c", "3d", "4h"], "action": "call",
        "pot": 100, "call_cost": 20, "range_sources": ["tight", "loose"],
        "human_reviewed": True, "variant": "PLO5", "start_pts": 10, "end_pts": 20,
    }


def valid_comparison():
    return {
        "status": "CONDITIONAL_ONLY",
        "cross_range_comparison_available": True,
        "hand_error_verified": False, "gto_solution": False,
        "stable_action": "call", "range_sensitive_or_inconclusive": False,
    }


class CommentaryGateRegression(unittest.TestCase):
    def test_reviewed_flop_allows_conditional_commentary(self):
        self.assertEqual(assess_conditional_commentary(valid_hand(), valid_comparison())["status"],
                         "CONDITIONAL_EXPLANATION_ALLOWED")

    def test_preflop_or_partial_board_does_not_authorize_commentary(self):
        for board in ([], ["2c"], ["2c", "3d"]):
            with self.subTest(board=board):
                hand = valid_hand()
                hand["board_cards"] = board
                result = assess_conditional_commentary(hand, valid_comparison())
                self.assertEqual(result["status"], "REVIEW_ONLY")
                self.assertIn("invalid_card_count", result["reasons"])

    def test_range_sensitive_cannot_also_claim_stable_action(self):
        comparison = valid_comparison()
        comparison["range_sensitive_or_inconclusive"] = True
        result = assess_conditional_commentary(valid_hand(), comparison)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertIn("contradictory_stability", result["reasons"])

    def test_non_sensitive_requires_stable_action(self):
        comparison = valid_comparison()
        comparison["stable_action"] = None
        result = assess_conditional_commentary(valid_hand(), comparison)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertIn("missing_stable_action", result["reasons"])

    def test_inconclusive_without_stable_action_remains_conditional(self):
        comparison = valid_comparison()
        comparison["stable_action"] = None
        comparison["range_sensitive_or_inconclusive"] = True
        self.assertEqual(assess_conditional_commentary(valid_hand(), comparison)["status"],
                         "CONDITIONAL_EXPLANATION_ALLOWED")


if __name__ == "__main__":
    unittest.main()
