"""Synthetic regression tests for offline Monte Carlo PLO5/PLO6."""
import unittest
from .offline_omaha_monte_carlo import sample_showdown_shares

H = ["As", "Ks", "Qs", "Js", "Ts"]
V = ["2c", "3c", "4c", "5c", "6c"]
B = ["7d", "8d", "9d", "Td", "Jd"]

class MonteCarloTests(unittest.TestCase):
    def sample(self):
        return sample_showdown_shares(hero=H, board=B, opponent_ranges=[[V]], iterations=4, seed=17)

    def test_reproducible(self):
        self.assertEqual(self.sample(), self.sample())

    def test_full_board(self):
        result = self.sample()
        self.assertEqual(result["attempts"], 4)
        self.assertEqual(len(result["shares"]), 4)
        self.assertTrue(all(0 <= x <= 1 for x in result["shares"]))

    def test_incomplete_board(self):
        result = sample_showdown_shares(hero=H, board=B[:3], opponent_ranges=[[V]], iterations=3, seed=5)
        self.assertEqual(len(result["shares"]), 3)

    def test_plo6(self):
        result = sample_showdown_shares(hero=H + ["2s"], board=B,
                                        opponent_ranges=[[V + ["3s"]]], iterations=2)
        self.assertEqual(result["iterations"], 2)

    def test_attempt_limit(self):
        with self.assertRaises(ValueError):
            sample_showdown_shares(hero=H, board=B, opponent_ranges=[[V]],
                                   iterations=4, max_attempts=3)

    def test_impossible_range(self):
        with self.assertRaisesRegex(ValueError, "insufficient compatible"):
            sample_showdown_shares(hero=H, board=B, opponent_ranges=[[H]],
                                   iterations=2, max_attempts=3)

    def test_duplicate_range_combo(self):
        with self.assertRaisesRegex(ValueError, "duplicate range"):
            sample_showdown_shares(hero=H, board=B, opponent_ranges=[[V, V]], iterations=1)

    def test_overlap(self):
        with self.assertRaises(ValueError):
            sample_showdown_shares(hero=H, board=["As"], opponent_ranges=[[V]], iterations=1)

    def test_boolean_iterations(self):
        with self.assertRaises(ValueError):
            sample_showdown_shares(hero=H, board=B, opponent_ranges=[[V]], iterations=True)

    def test_not_gto(self):
        self.assertFalse(self.sample()["gto_solution"])

if __name__ == "__main__":
    unittest.main()
