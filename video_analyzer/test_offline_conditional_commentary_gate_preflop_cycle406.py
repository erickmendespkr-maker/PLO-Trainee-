"""Regression: preflop decisions must remain review-only until street-aware evidence is supported."""
import unittest

try:
    from video_analyzer.offline_conditional_commentary_gate import assess_conditional_commentary
except ImportError:
    from offline_conditional_commentary_gate import assess_conditional_commentary


def reviewed_hand(board):
    return {
        "table_id": "table-1", "hand_id": "hand-1",
        "video_sha256": "a" * 64, "hero_cards": ["Ac", "Kd", "Qh", "Js", "Tc"],
        "board_cards": board, "action": "call", "pot": 100.0,
        "call_cost": 20.0, "range_sources": ["tight", "loose"],
        "human_reviewed": True, "variant": "PLO5",
        "start_pts": 10.0, "end_pts": 20.0,
    }


COMPARISON = {
    "status": "CONDITIONAL_ONLY",
    "cross_range_comparison_available": True,
    "hand_error_verified": False,
    "gto_solution": False,
    "stable_action": None,
    "range_sensitive_or_inconclusive": True,
}


class StreetGateTests(unittest.TestCase):
    def test_preflop_not_yet_supported(self):
        result = assess_conditional_commentary(reviewed_hand([]), COMPARISON)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertIn("invalid_card_count", result["reasons"])
        self.assertFalse(result["verified_error"])

    def test_partial_flop_not_supported(self):
        for board in (["2c"], ["2c", "3d"]):
            with self.subTest(board=board):
                result = assess_conditional_commentary(reviewed_hand(board), COMPARISON)
                self.assertEqual(result["status"], "REVIEW_ONLY")

    def test_valid_flop_is_conditional_only(self):
        result = assess_conditional_commentary(reviewed_hand(["2c", "3d", "4h"]), COMPARISON)
        self.assertEqual(result["status"], "CONDITIONAL_EXPLANATION_ALLOWED")
        self.assertFalse(result["verified_error"])
        self.assertTrue(result["range_sensitive_or_inconclusive"])

    def test_duplicate_board_card_is_rejected(self):
        result = assess_conditional_commentary(reviewed_hand(["2c", "2c", "4h"]), COMPARISON)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertIn("duplicate_cards", result["reasons"])


if __name__ == "__main__":
    unittest.main()
