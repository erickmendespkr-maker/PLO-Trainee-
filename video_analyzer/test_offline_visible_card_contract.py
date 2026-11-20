import unittest
from offline_visible_card_contract import validate_fields

BASE = {'hero_cards':['As','Ks','Qs','Js','Ts'], 'board_cards':['2c','3d','4h'], 'action':'call','pot':100,'call_cost':50}
class Tests(unittest.TestCase):
    def check_bad(self, key, value):
        d = dict(BASE); d[key] = value
        with self.assertRaises(ValueError): validate_fields(d)
    def test_valid_plo5(self): validate_fields(BASE)
    def test_valid_plo6(self):
        d=dict(BASE);d['hero_cards']=BASE['hero_cards']+['9s'];validate_fields(d)
    def test_duplicate(self): self.check_bad('board_cards',['As','3d','4h'])
    def test_bad_rank(self): self.check_bad('hero_cards',['1s']+BASE['hero_cards'][1:])
    def test_wrong_count(self): self.check_bad('hero_cards',BASE['hero_cards'][:4])
    def test_wrong_board_count(self): self.check_bad('board_cards',['2c','3d'])
    def test_negative_pot(self): self.check_bad('pot',-1)
    def test_nan_cost(self): self.check_bad('call_cost',float('nan'))
    def test_boolean_money(self): self.check_bad('pot',True)
    def test_unknown_action(self): self.check_bad('action','win')
    def test_free_call(self): self.check_bad('call_cost',0)
    def test_empty_board(self):
        d=dict(BASE);d['board_cards']=[];validate_fields(d)
if __name__=='__main__': unittest.main()
