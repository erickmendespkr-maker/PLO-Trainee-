"""Regression: Omaha hole-card order must not overweight Monte Carlo ranges."""
import unittest

from .offline_omaha_monte_carlo import sample_showdown_shares


HERO = ("As", "Kd", "Qc", "Jh", "Ts")
OPP = ("2s", "3d", "4c", "5h", "6s")


class RangeCanonicalizationTests(unittest.TestCase):
    def test_reordered_combo_is_duplicate(self):
        with self.assertRaisesRegex(ValueError, "reordered"):
            sample_showdown_shares(
                hero=HERO, board=(),
                opponent_ranges=[[OPP, tuple(reversed(OPP))]],
                iterations=1, seed=17,
            )

    def test_distinct_combos_are_not_rejected_as_duplicates(self):
        alternative = ("2s", "3d", "4c", "5h", "7s")
        result = sample_showdown_shares(
            hero=HERO, board=(),
            opponent_ranges=[[OPP, alternative]],
            iterations=1, seed=17,
        )
        self.assertEqual(result["iterations"], 1)
        self.assertEqual(len(result["shares"]), 1)


if __name__ == "__main__":
    unittest.main()
