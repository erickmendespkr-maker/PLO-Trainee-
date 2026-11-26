import unittest
from unittest.mock import patch
from PIL import Image
from plo5_seat_candidates import observe,conditional_positions,SEATS,GLYPHS,CENTERS
from plo5_mixed_money import STARTS

class SeatTests(unittest.TestCase):
    def test_marker_all_seats(self):
        for platform in CENTERS:
            for t in (1,4):
                for seat,(x,y) in zip(SEATS,CENTERS[platform]):
                    im=Image.new('RGB',(1504,696),(30,48,80));glyph=Image.frombytes('L',(14,14),bytes.fromhex(GLYPHS[platform])).convert('RGB');im.paste(glyph,(STARTS[t-1]+x-7,y-7))
                    with patch('plo5_seat_candidates.detect',return_value=platform):
                        r=observe(im,t);self.assertEqual(r['dealer_seat_candidate'],seat);self.assertIsNone(r['hero_position']);self.assertFalse(r['positions_verified'])
    def test_double_marker_rejected(self):
        im=Image.new('RGB',(1504,696));g=Image.frombytes('L',(14,14),bytes.fromhex(GLYPHS['suprema'])).convert('RGB')
        for x,y in CENTERS['suprema'][:2]:im.paste(g,(x-7,y-7))
        with patch('plo5_seat_candidates.detect',return_value='suprema'):self.assertIsNone(observe(im,1)['dealer_seat_candidate'])
    def test_no_marker(self):
        with patch('plo5_seat_candidates.detect',return_value='pppoker'):self.assertIsNone(observe(Image.new('RGB',(1504,696)),1)['dealer_seat_candidate'])
    def test_hero_requires_bound_cards(self):
        c={'table_id':1,'platform':'pppoker','variant':5,'hero_cards':['Ac','Kd','Qh','Js','Tc']}
        im=Image.new('RGB',(1504,696))
        with patch('plo5_seat_candidates.detect',return_value='pppoker'):
            self.assertEqual(observe(im,1,c)['hero_seat_candidate'],'hero_bottom');self.assertIsNone(observe(im,2,c)['hero_seat_candidate']);self.assertFalse(observe(im,1,c)['hero_identity_verified'])
    def test_positions(self):
        self.assertEqual(conditional_positions('top',list(SEATS),standard_blinds=True)['hero_bottom'],'UTG')
        self.assertEqual(conditional_positions('hero_bottom',['hero_bottom','top'],standard_blinds=True),{'hero_bottom':'BTN/SB','top':'BB'})
        self.assertEqual(conditional_positions('top',['top','hero_bottom','lower_left','upper_left'],standard_blinds=True)['hero_bottom'],'SB')
    def test_abstain(self):
        for d in (None,[],['top','top'],['top','bad'],['hero_bottom','lower_left']):self.assertIsNone(conditional_positions('top',d,standard_blinds=True))
        self.assertIsNone(conditional_positions('top',list(SEATS)))
    def test_unknown(self):
        with patch('plo5_seat_candidates.detect',return_value=None):self.assertEqual(observe(None,1)['scores'],[])

if __name__=='__main__':unittest.main()
