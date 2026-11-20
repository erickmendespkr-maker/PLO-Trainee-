import unittest
from offline_hand_timeline import Observation, propose_intervals

class TimelineTests(unittest.TestCase):
    def test_reset_is_unverified(self):
        out = propose_intervals([Observation('1', 1, 'river', ('As','Kd','Qh','2c','3s'), .9), Observation('1', 3, 'preflop', (), .8)], 10)
        self.assertEqual(out[0]['reason'], 'street_reset')
        self.assertFalse(out[0]['verified_by_human'])
        self.assertFalse(out[0]['boundary_exact'])
        self.assertEqual(out[0]['confidence_upper_bound'], .8)
    def test_board_change(self):
        a = Observation('1', 1, 'flop', ('As','Kd','Qh'), .7)
        b = Observation('1', 2, 'turn', ('As','Kd','Qh','2c'), .6)
        self.assertEqual(propose_intervals([b,a], 10)[0]['reason'], 'board_change')
    def test_separate_tables(self):
        self.assertEqual(propose_intervals([Observation('1', 1, 'flop'), Observation('2', 2, 'river')], 10), [])
    def test_bad_time(self):
        with self.assertRaises(ValueError): propose_intervals([Observation('1', 11, 'flop')], 10)
    def test_duplicate_time(self):
        with self.assertRaises(ValueError): propose_intervals([Observation('1', 1, 'flop'), Observation('1', 1, 'turn')], 10)
    def test_invalid_confidence(self):
        with self.assertRaises(ValueError): propose_intervals([Observation('1', 1, 'flop', confidence=float('nan'))], 10)
    def test_invalid_duration(self):
        with self.assertRaises(ValueError): propose_intervals([], float('inf'))
    def test_no_observations(self):
        self.assertEqual(propose_intervals([], 10), [])

if __name__ == '__main__': unittest.main()
