import unittest
from plo5_error_selection import select_errors


def decision(actual_bounds, alternative_bounds, **overrides):
    d = dict(hand_id="h", decision_id="d", street="river", action="a",
             reconstruction_verified=True, strategy_verified=True,
             action_ev_bounds={"a": actual_bounds, "b": alternative_bounds})
    d.update(overrides)
    return d


class ErrorSelectionTests(unittest.TestCase):
    def test_adequate_with_interval(self):
        r = select_errors([decision((3, 5), (0, 2))])
        self.assertEqual(r["adequate"], [("h", "d")])
        self.assertFalse(r["unresolved"])

    def test_tie(self):
        self.assertEqual(len(select_errors([decision((1, 1), (1, 1))])["adequate"]), 1)

    def test_touching_bounds(self):
        self.assertEqual(len(select_errors([decision((2, 3), (0, 2))])["adequate"]), 1)

    def test_overlap(self):
        self.assertEqual(len(select_errors([decision((1, 3), (2, 4))])["unresolved"]), 1)

    def test_confirmed_error(self):
        r = select_errors([decision((0, 1), (3, 4))])["errors"][0]
        self.assertEqual((r["recommended"], r["ev_loss_lower_bb"], r["ev_loss_upper_bb"]), ("b", 2, 4))

    def test_unverified(self):
        self.assertEqual(len(select_errors([decision((0, 1), (3, 4), strategy_verified=False)])["unresolved"]), 1)

    def test_duplicate(self):
        d = decision((0, 1), (3, 4))
        with self.assertRaises(ValueError):
            select_errors([d, d])

    def test_invalid(self):
        for bounds in [(2, 1), (0, float("inf")), (float("nan"), 2)]:
            with self.assertRaises(ValueError):
                select_errors([decision(bounds, (3, 4))])

    def test_multiple_alternatives(self):
        d = decision((0, 1), (3, 4), action_ev_bounds={"a": (0, 1), "b": (3, 4), "c": (2, 9)})
        r = select_errors([d])["errors"][0]
        self.assertEqual((r["recommended"], r["ev_loss_lower_bb"], r["ev_loss_upper_bb"]), ("b", 2, 9))

    def test_missing_alternative(self):
        self.assertEqual(len(select_errors([decision((0, 1), (3, 4), action_ev_bounds={"a": (0, 1)})])["unresolved"]), 1)


if __name__ == "__main__":
    unittest.main()
