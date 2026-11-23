"""Synthetic regression checks for bounded-share equity uncertainty."""
import unittest
from .offline_equity_ci_audit import bounded_share_interval


class AuditTests(unittest.TestCase):
    def test_balanced(self):
        r = bounded_share_interval([0, 1] * 500)
        self.assertEqual(r["equity"], .5)
        self.assertLess(r["equity_ci"][0], .5)
        self.assertGreater(r["equity_ci"][1], .5)

    def test_degenerate_not_zero_width(self):
        r = bounded_share_interval([1] * 100)
        self.assertLess(r["equity_ci"][0], 1)

    def test_ties(self):
        r = bounded_share_interval([.5] * 100)
        self.assertEqual(r["equity"], .5)

    def test_invalid(self):
        for x in ([0], [0, float("nan")], [0, True], [0, 2]):
            with self.assertRaises(ValueError):
                bounded_share_interval(x)

    def test_more_samples_narrower(self):
        a = bounded_share_interval([0, 1] * 50)
        b = bounded_share_interval([0, 1] * 500)
        self.assertLess(b["equity_ci"][1] - b["equity_ci"][0],
                        a["equity_ci"][1] - a["equity_ci"][0])


if __name__ == "__main__":
    unittest.main()
