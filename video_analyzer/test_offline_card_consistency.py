import unittest
from offline_card_consistency import validate_visible_cards as check

H5 = ['As','Kd','Qc','Jh','Ts']
H6 = H5 + ['9d']
B = ['2c','3c','4c','5c','6c']

class CardConsistencyTests(unittest.TestCase):
    def test_plo5_river(self):
        self.assertEqual(check(H5,B,'PLO5')['status'], 'CONSISTENT')
    def test_plo6_flop(self):
        self.assertEqual(check(H6,B[:3],'PLO6')['status'], 'CONSISTENT')
    def test_preflop_allowed(self):
        self.assertEqual(check(H5,[],'PLO5')['status'], 'CONSISTENT')
    def test_hero_count(self):
        self.assertIn('hero_card_count',check(H5,'','PLO6')['problems'])
    def test_board_count(self):
        self.assertIn('board_card_count',check(H5,B[:2],'PLO5')['problems'])
    def test_duplicate_across_hero_and_board(self):
        self.assertIn('duplicate_card',check(H5,['As','2c','3c'],'PLO5')['problems'])
    def test_invalid_rank(self):
        self.assertIn('invalid_card',check(['1s']+H5[1:],B,'PLO5')['problems'])
    def test_invalid_suit(self):
        self.assertIn('invalid_card',check(['Ax']+H5[1:],B,'PLO5')['problems'])
    def test_unknown_is_not_assumed(self):
        self.assertIn('invalid_card',check(['??']+H5[1:],B,'PLO5')['problems'])
    def test_unsupported_variant(self):
        self.assertIn('unsupported_variant',check(H5,B,'PLO4')['problems'])
    def test_no_strategy_claim(self):
        self.assertFalse(check(H5,B,'PLO5')['strategic_verification'])
    def test_non_string_card(self):
        self.assertIn('invalid_card',check([None]+H5[1:],B,'PLO5')['problems'])

if __name__ == '__main__': unittest.main()
