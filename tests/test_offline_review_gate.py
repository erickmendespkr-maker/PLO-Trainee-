"""Regression tests for offline review gate; synthetic data only."""
import unittest
from video_analyzer.offline_review_gate import REQUIRED, review_gate


def sample():
    return dict(table_id="mesa-1", hand_id="h1", start_s=10, end_s=20,
                hero_cards=["AS", "KS", "QS", "JS", "TS"],
                board=["2C", "3D", "4H"], action="call",
                pot_before=100, cost_to_call=25, verified_fields=list(REQUIRED))


class ReviewGateTests(unittest.TestCase):
    def gate(self, hand, variant="PLO5"):
        return review_gate(hand, video_duration_s=60, variant=variant)

    def test_reviewed(self):
        self.assertEqual(self.gate(sample())["status"], "READY_FOR_CONDITIONAL_ANALYSIS")

    def test_unreviewed(self):
        hand = sample()
        hand["verified_fields"] = []
        self.assertEqual(self.gate(hand)["status"], "INSUFFICIENT_DATA")

    def test_missing_action(self):
        hand = sample()
        del hand["action"]
        self.assertIn("action", self.gate(hand)["missing_fields"])

    def test_duplicate_cards(self):
        hand = sample()
        hand["board"][0] = "as"
        self.assertIn("duplicate_cards", self.gate(hand)["invalid_fields"])

    def test_time_window(self):
        hand = sample()
        hand["end_s"] = 61
        self.assertIn("time_window", self.gate(hand)["invalid_fields"])

    def test_plo6(self):
        hand = sample()
        hand["hero_cards"].append("9S")
        self.assertEqual(self.gate(hand, "PLO6")["status"], "READY_FOR_CONDITIONAL_ANALYSIS")

    def test_nan(self):
        hand = sample()
        hand["pot_before"] = float("nan")
        self.assertIn("pot_before", self.gate(hand)["invalid_fields"])

    def test_no_gto_claim(self):
        result = self.gate(sample())
        self.assertFalse(result["is_gto_solution"])
        self.assertIsNone(result["strategic_conclusion"])


if __name__ == "__main__":
    unittest.main()
