import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_suprema_suits import regions, classify, observe, HERO_X, BOARD_X
from plo5_mixed_money import STARTS

class SupremaSuitsTests(unittest.TestCase):
    def test_geometry(self):
        im=Image.new('RGB',(1504,696));d=ImageDraw.Draw(im)
        for t,x in enumerate(STARTS,1):
            for f,xs,y in [('hero',HERO_X,546),('board',BOARD_X,253)]:
                for i,a in enumerate(xs):
                    d.point((x+a+2,y+2),fill=(t,i,1));r,s=regions(im,t,f,i)
                    self.assertEqual(r.getpixel((0,0)),(t,i,1))
                    self.assertEqual(r.size,(14,15) if f=='hero' else (20,21))
    def test_invalid_geometry(self):
        im=Image.new('RGB',(1504,696))
        for args in [(im,0,'hero',0),(im,4,'bad',0),(im,1,'board',5),(Image.new('RGB',(1,1)),1,'hero',0)]:
            with self.assertRaises(ValueError):regions(*args)
    def test_suit_candidates(self):
        for s in 'cdhs':
            with patch('plo5_suprema_suits.feature',return_value=(s,s,(b'1',1),.7,.7,False)):
                r=classify(None,1,'hero',0);self.assertEqual(r['suit'],s);self.assertIsNone(r['card']);self.assertIsNone(r['rank'])
    def test_color_disagreement(self):
        with patch('plo5_suprema_suits.feature',return_value=('c','d',(b'1',1),.7,.7,False)):
            self.assertIsNone(classify(None,1,'hero',0)['suit'])
    def test_background_required(self):
        with patch('plo5_suprema_suits.feature',return_value=('d','d',(b'1',1),0,0,False)):
            self.assertIsNone(classify(None,1,'hero',0)['suit'])
    def test_blue_felt(self):
        im=Image.new('RGB',(1504,696),(30,48,80))
        self.assertEqual(classify(im,1,'board',0)['status'],'felt_empty_candidate')
        self.assertEqual(classify(im,1,'hero',0)['status'],'uncertain')
    def test_unsupported_platform(self):
        with patch('plo5_suprema_suits.detect',return_value='pppoker'),patch('plo5_suprema_suits.classify') as c:
            r=observe(None,1);c.assert_not_called();self.assertEqual(r['hero_slots'],[])
    def test_no_full_card_claims(self):
        with patch('plo5_suprema_suits.detect',return_value='suprema'),patch('plo5_suprema_suits.classify',return_value={'suit':'c'}):
            r=observe(None,1);self.assertEqual(len(r['hero_slots']),5);self.assertEqual(len(r['board_slots']),5);self.assertFalse(r['cards_verified']);self.assertIsNone(r['hero_cards']);self.assertIsNone(r['board_cards'])
if __name__=='__main__':unittest.main()
