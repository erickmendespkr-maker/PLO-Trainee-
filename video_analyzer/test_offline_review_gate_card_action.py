"""Regression tests for the conservative video evidence gate."""
import unittest

try:
    from video_analyzer.offline_review_gate import review_gate
except ModuleNotFoundError:
    from offline_review_gate import review_gate


class ReviewGateCardActionTests(unittest.TestCase):
    def setUp(self):
        self.hand = dict(table_id="table-A", hand_id="h1", start_s=1.0,
                         end_s=2.0, hero_cards=["As", "Kd", "Qc", "Jh", "Ts"],
                         board=["2s", "3d", "4c"], action="call",
                         pot_before=20.0, cost_to_call=5.0)
        self.hand["verified_fields"] = list(self.hand.keys())

    def check_invalid(self, key, value):
        hand = dict(self.hand)
        hand[key] = value
        result = review_gate(hand, video_duration_s=10, variant="PLO5")
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIn(key, result["invalid_fields"])

    def test_valid_observation(self):
        result = review_gate(self.hand, video_duration_s=10, variant="PLO5")
        self.assertEqual(result["status"], "READY_FOR_CONDITIONAL_ANALYSIS")
        self.assertIsNone(result["strategic_conclusion"])

    def test_reject_invalid_card(self):
        for bad in ("1s", "ZZ", "10h", "A?", "joker"):
            with self.subTest(bad=bad):
                self.check_invalid("hero_cards", ["As", "Kd", "Qc", "Jh", bad])

    def test_reject_invalid_board(self):
        self.check_invalid("board", ["2s", "3d", "??"])

    def test_reject_unsupported_action(self):
        self.check_invalid("action", "teleport")

    def test_fold_facing_bet_is_valid(self):
        hand = dict(self.hand, action="fold")
        result = review_gate(hand, video_duration_s=10, variant="PLO5")
        self.assertEqual(result["status"], "READY_FOR_CONDITIONAL_ANALYSIS")

    def test_duplicate_case_insensitive(self):
        self.check_invalid("hero_cards", ["As", " aS ", "Qc", "Jh", "Ts"])


if __name__ == "__main__":
    unittest.main()
