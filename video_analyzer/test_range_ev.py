import unittest
from itertools import combinations
from equity import DECK
from range_ev import WeightedHand, estimate_weighted_range_equity, heads_up_all_in_raise_ev


class WeightedRangeTests(unittest.TestCase):
    HERO = ('As', 'Ks', '2d', '3c', '4h')
    BOARD = ('Qs', 'Js', 'Ts', '9d', '8c')
    LOSING = ('2c', '3d', '4c', '5d', '6h')
    TIE = ('Ah', 'Kh', '2h', '3h', '4d')

    def test_known_winner_vs_weighted_loser(self):
        result = estimate_weighted_range_equity(self.HERO, self.BOARD,
                                                [WeightedHand(self.LOSING, 1)], trials=10, seed=2)
        self.assertEqual(result.wins, 10)
        self.assertEqual(result.equity, 1.)
        self.assertEqual(result.opponent_model, 'user_weighted_opponent_range')

    def test_reproducibility_and_partial_board(self):
        args = (self.HERO, self.BOARD[:3], [WeightedHand(self.LOSING, 1)])
        a = estimate_weighted_range_equity(*args, trials=11, seed=12)
        self.assertEqual(a, estimate_weighted_range_equity(*args, trials=11, seed=12))
        self.assertEqual(a.wins + a.losses + a.ties, 11)

    def test_reject_duplicate_range_hand(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate opponent'):
            estimate_weighted_range_equity(self.HERO, self.BOARD,
                [WeightedHand(self.LOSING, 1), WeightedHand(tuple(reversed(self.LOSING)), 1)])

    def test_reject_colliding_known_cards(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate cards'):
            estimate_weighted_range_equity(self.HERO, self.BOARD,
                [WeightedHand(('As', '2c', '3d', '4c', '5d'), 1)])

    def test_reject_invalid_weight(self):
        with self.assertRaisesRegex(ValueError, 'range weight'):
            estimate_weighted_range_equity(self.HERO, self.BOARD,
                [WeightedHand(self.LOSING, float('nan'))])

    def test_reject_empty_range(self):
        with self.assertRaisesRegex(ValueError, 'positive-weight'):
            estimate_weighted_range_equity(self.HERO, self.BOARD, [])

    def test_reject_unbounded_trial_count(self):
        for trials in (0, True, 50001, 2.5):
            with self.subTest(trials=trials), self.assertRaisesRegex(ValueError, 'trials'):
                estimate_weighted_range_equity(self.HERO, self.BOARD,
                                               [WeightedHand(self.LOSING, 1)], trials=trials)

    def test_reject_nonfinite_sum_of_weights(self):
        with self.assertRaisesRegex(ValueError, 'Sum of range weights'):
            estimate_weighted_range_equity(self.HERO, self.BOARD,
                [WeightedHand(self.LOSING, 1e308), WeightedHand(self.TIE, 1e308)])

    def test_reject_oversized_range_without_consuming_generator(self):
        available = [card for card in DECK if card not in self.HERO + self.BOARD]
        def unbounded():
            for hand in combinations(available, 5):
                yield WeightedHand(hand, 1.)
        with self.assertRaisesRegex(ValueError, 'Range exceeds'):
            estimate_weighted_range_equity(self.HERO, self.BOARD, unbounded())

    def test_raise_ev_when_everyone_folds(self):
        self.assertEqual(heads_up_all_in_raise_ev(.2, 100, 50, 50, 1.), 100)

    def test_raise_ev_when_always_called(self):
        self.assertEqual(heads_up_all_in_raise_ev(.4, 100, 50, 50, 0.), 30)

    def test_raise_ev_with_fold_equity(self):
        self.assertEqual(heads_up_all_in_raise_ev(.4, 100, 50, 50, .5), 65)

    def test_raise_ev_reject_invalid_probability(self):
        with self.assertRaisesRegex(ValueError, 'fold_probability'):
            heads_up_all_in_raise_ev(.4, 100, 50, 50, 1.5)


if __name__ == '__main__':
    unittest.main()
