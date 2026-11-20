import unittest
from offline_street_consistency import Observation, validate_observation, review_sequence


def o(t, street='flop', board=('As', 'Kd', '2c'), table=1, hand='h1', conf=.8):
    return Observation(t, street, board, table, hand, conf)


class StreetConsistencyTests(unittest.TestCase):
    def test_valid_progression(self):
        self.assertEqual(review_sequence([o(1), o(2, 'turn', ('As','Kd','2c','Th')), o(3, 'river', ('As','Kd','2c','Th','9s'))])['status'], 'CONSISTENT_OBSERVATIONS_ONLY')
    def test_bad_count(self):
        self.assertIn('board_count_street_mismatch', validate_observation(o(1, 'river')))
    def test_duplicate(self):
        self.assertIn('duplicate_card', validate_observation(o(1, board=('As','As','2c'))))
    def test_invalid_card(self):
        self.assertIn('invalid_card', validate_observation(o(1, board=('1s','Kd','2c'))))
    def test_hole_variant(self):
        self.assertIn('hole_count_variant_mismatch', validate_observation(o(1), ['3c']*4, 'PLO5'))
    def test_hole_collision(self):
        self.assertIn('duplicate_card', validate_observation(o(1), ['As','3c','4d','5h','6s'], 'PLO5'))
    def test_regression(self):
        self.assertIn('street_regression', review_sequence([o(1, 'turn', ('As','Kd','2c','Th')), o(2)])['errors'])
    def test_board_change(self):
        self.assertIn('board_changed', review_sequence([o(1), o(2, board=('Ah','Kd','2c'))])['errors'])
    def test_pts(self):
        self.assertIn('non_increasing_pts', review_sequence([o(2), o(2)])['errors'])
    def test_mixed(self):
        self.assertIn('mixed_hand_or_table', review_sequence([o(1), o(2, hand='h2')])['errors'])
    def test_empty(self):
        self.assertEqual(review_sequence([])['status'], 'INSUFFICIENT_DATA')
    def test_nan(self):
        self.assertIn('invalid_pts', validate_observation(o(float('nan'))))
    def test_no_promotion(self):
        self.assertFalse(review_sequence([o(1)])['strategic_conclusion_allowed'])

if __name__ == '__main__':
    unittest.main()
