"""Synthetic exact river enumeration checks."""
import unittest
from .offline_exact_river_equity import exact_river_equity

HERO = ["As", "Ks", "Qs", "Js", "Ts"]
BOARD = ["2c", "3d", "4h", "5c", "6d"]

class ExactRiverTests(unittest.TestCase):
    def test_win_and_loss(self):
        result = exact_river_equity(hero=HERO, board=BOARD, opponent_range=[
            ["7c", "8c", "9c", "Tc", "Jc"],
            ["7d", "8d", "9d", "Td", "Jd"]])
        self.assertEqual(result["legal_combos"], 2)
        self.assertEqual(result["equity"], 0.0)
        self.assertFalse(result["gto_solution"])

    def test_blocker_exclusion(self):
        result = exact_river_equity(hero=HERO, board=BOARD, opponent_range=[
            ["As", "7c", "8c", "9c", "Tc"],
            ["7c", "8c", "9c", "Tc", "Jc"]])
        self.assertEqual(result["excluded_by_blockers"], 1)
        self.assertEqual(result["legal_combos"], 1)

    def test_reordered_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            exact_river_equity(hero=HERO, board=BOARD, opponent_range=[
                ["7c", "8c", "9c", "Tc", "Jc"],
                ["Jc", "Tc", "9c", "8c", "7c"]])

    def test_no_legal_combo(self):
        with self.assertRaises(ValueError):
            exact_river_equity(hero=HERO, board=BOARD, opponent_range=[
                ["As", "7c", "8c", "9c", "Tc"]])

    def test_plo6(self):
        result = exact_river_equity(hero=HERO + ["9s"], board=BOARD,
            opponent_range=[["7c", "8c", "9c", "Tc", "Jc", "Qc"]])
        self.assertEqual(result["legal_combos"], 1)

if __name__ == "__main__":
    unittest.main()
