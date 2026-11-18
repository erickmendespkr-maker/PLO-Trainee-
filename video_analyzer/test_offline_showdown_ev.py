"""Independent deterministic payoff benchmarks; no poker footage required."""
import unittest
from video_analyzer.offline_showdown_ev import showdown_call_ev


class TestShowdownEV(unittest.TestCase):
    def test_certain_loss(self):
        self.assertEqual(showdown_call_ev(100, 50, [{'probability': 1, 'hero_share': 0}])['call_ev'], -50)

    def test_certain_win(self):
        self.assertEqual(showdown_call_ev(100, 50, [{'probability': 1, 'hero_share': 1}])['call_ev'], 100)

    def test_break_even(self):
        x = showdown_call_ev(100, 50, [{'probability': 1/3, 'hero_share': 1}, {'probability': 2/3, 'hero_share': 0}])
        self.assertAlmostEqual(x['call_ev'], 0)

    def test_split_pot(self):
        self.assertEqual(showdown_call_ev(100, 50, [{'probability': 1, 'hero_share': .5}])['call_ev'], 25)

    def test_split_pot_rake(self):
        self.assertEqual(showdown_call_ev(100, 50, [{'probability': 1, 'hero_share': .5}], rake=10)['call_ev'], 20)

    def test_probability_weighted_win_tie_loss(self):
        x = showdown_call_ev(100, 50, [{'probability': .4, 'hero_share': 1}, {'probability': .2, 'hero_share': .5}, {'probability': .4, 'hero_share': 0}])
        self.assertAlmostEqual(x['call_ev'], 25)

    def test_reject_non_normalized(self):
        with self.assertRaises(ValueError):
            showdown_call_ev(100, 50, [{'probability': .9, 'hero_share': 1}])

    def test_reject_bad_inputs(self):
        cases = [(-1, 50, [{'probability': 1, 'hero_share': 1}], 0),
                 (100, 0, [{'probability': 1, 'hero_share': 1}], 0),
                 (100, 50, [{'probability': 1, 'hero_share': 1}], 151),
                 (100, 50, [{'probability': float('nan'), 'hero_share': 1}], 0),
                 (100, 50, [{'probability': 1, 'hero_share': 1.2}], 0),
                 (100, 50, [{'probability': True, 'hero_share': 1}], 0)]
        for p, c, o, r in cases:
            with self.subTest(p=p, c=c, o=o, r=r), self.assertRaises(ValueError):
                showdown_call_ev(p, c, o, rake=r)

    def test_no_gto_claim(self):
        x = showdown_call_ev(100, 50, [{'probability': 1, 'hero_share': 1}])
        self.assertFalse(x['gto_claim_permitted'])
        self.assertFalse(x['automatic_blunder_label_permitted'])


if __name__ == '__main__':
    unittest.main()
