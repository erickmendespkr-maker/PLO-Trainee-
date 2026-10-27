"""Deterministic known-showdown checks, independent of random runout."""
import unittest
import offline_omaha_equity_mc as m

BOARD = ["Ah", "Kh", "Qh", "9c", "8d"]
FLUSH = ["2h", "3h", "4c", "5s", "6d"]
HIGH = ["2c", "3d", "4s", "5c", "6s"]


def scenario(hero, villain, board, game="PLO5"):
    return {"schema_version": 1, "game_type": game,
            "hero_hole": hero, "known_board": board,
            "explicit_villain_hands": [villain], "samples": 100, "seed": 13,
            "range_assumption": "One fully specified synthetic opponent hand."}


class KnownShowdownTests(unittest.TestCase):
    def test_hero_always_wins_with_two_private_hearts(self):
        result = m.estimate(scenario(FLUSH, HIGH, BOARD))
        self.assertEqual((result["wins"], result["ties"], result["losses"]), (100, 0, 0))
        self.assertEqual(result["equity_estimate"], 1.0)

    def test_hero_always_loses_without_heart_hole_cards(self):
        result = m.estimate(scenario(HIGH, FLUSH, BOARD))
        self.assertEqual((result["wins"], result["ties"], result["losses"]), (0, 0, 100))
        self.assertEqual(result["equity_estimate"], 0.0)

    def test_equal_broadway_is_half_equity(self):
        hero = ["As", "Kd", "4d", "5c", "6h"]
        villain = ["Ah", "Kc", "4c", "5d", "6s"]
        board = ["Qc", "Jd", "Th", "2s", "3c"]
        result = m.estimate(scenario(hero, villain, board))
        self.assertEqual((result["wins"], result["ties"], result["losses"]), (0, 100, 0))
        self.assertEqual(result["equity_estimate"], 0.5)

    def test_plo6_uses_exactly_two_private_cards(self):
        result = m.estimate(scenario(FLUSH + ["7c"], HIGH + ["7d"], BOARD, "PLO6"))
        self.assertEqual(result["wins"], 100)
        self.assertTrue(result["exactly_two_private_three_board"])


if __name__ == "__main__":
    unittest.main()
