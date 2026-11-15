"""Cross-check river Monte Carlo against exact enumeration with real Omaha evaluator.

Only synthetic cards and hypothetical uniform ranges; no video claims or GTO.
"""
import math
import unittest

from .offline_exact_river_equity import exact_river_equity
from .offline_omaha_monte_carlo import sample_showdown_shares

HERO = ["As", "Ks", "Qs", "Js", "Ts"]
BOARD = ["2d", "3d", "4d", "5d", "9c"]
RANGE = [
    ["6h", "7h", "8h", "9h", "Th"],
    ["2c", "3c", "4c", "5c", "6c"],
    ["Ad", "Kd", "Qd", "Jd", "Td"],
    ["2s", "3s", "4s", "5s", "6s"],
]


class ExactVsMonteCarloTests(unittest.TestCase):
    def test_same_single_combo_is_exact(self):
        exact = exact_river_equity(hero=HERO, board=BOARD, opponent_range=[RANGE[0]])
        mc = sample_showdown_shares(
            hero=HERO, board=BOARD, opponent_ranges=[[RANGE[0]]],
            iterations=32, seed=11,
        )
        self.assertAlmostEqual(sum(mc["shares"]) / 32, exact["equity"])
        self.assertEqual(mc["attempts"], 32)

    def test_multiple_uniform_combos_converge_to_exact(self):
        exact = exact_river_equity(hero=HERO, board=BOARD, opponent_range=RANGE)
        mc = sample_showdown_shares(
            hero=HERO, board=BOARD, opponent_ranges=[RANGE],
            iterations=2400, seed=2026,
        )
        mean = sum(mc["shares"]) / len(mc["shares"])
        # Hoeffding: P(|mean - expected| >= 0.08) <= 2 exp(-2*2400*.08**2)
        self.assertLessEqual(abs(mean - exact["equity"]), 0.08)
        self.assertFalse(mc["gto_solution"])
        self.assertFalse(exact["gto_solution"])

    def test_blocked_combo_excluded_in_both_methods(self):
        blocked = ["As", "6h", "7h", "8h", "9h"]
        exact = exact_river_equity(
            hero=HERO, board=BOARD, opponent_range=RANGE + [blocked],
        )
        mc = sample_showdown_shares(
            hero=HERO, board=BOARD, opponent_ranges=[RANGE + [blocked]],
            iterations=2400, seed=2026,
        )
        self.assertEqual(exact["excluded_by_blockers"], 1)
        self.assertEqual(exact["legal_combos"], len(RANGE))
        self.assertGreater(mc["attempts"], mc["iterations"])
        self.assertLessEqual(
            abs(sum(mc["shares"]) / len(mc["shares"]) - exact["equity"]), 0.08
        )

    def test_reordered_duplicate_rejected_by_both(self):
        duplicate = list(reversed(RANGE[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            exact_river_equity(hero=HERO, board=BOARD, opponent_range=RANGE + [duplicate])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            sample_showdown_shares(
                hero=HERO, board=BOARD, opponent_ranges=[RANGE + [duplicate]],
                iterations=1,
            )


if __name__ == "__main__":
    unittest.main()
