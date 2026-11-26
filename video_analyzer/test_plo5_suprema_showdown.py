import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_suprema_soft import showdown_regions, feature
from plo5_suprema_suits import BOARD_X, regions
from plo5_mixed_money import STARTS
from plo5_card_review import CardReader


def sample(indices):
    im=Image.new('RGB',(1504,696),(30,48,80));d=ImageDraw.Draw(im)
    for i in indices:
        x=BOARD_X[i];d.rectangle((x-2,244,x+43,247),fill=(230,190,10))
    return im


class ShowdownTests(unittest.TestCase):
    def test_three_borders(self):
        im=sample([0,1,4]);d=ImageDraw.Draw(im)
        d.point((BOARD_X[0],250),fill='red')
        d.point((BOARD_X[2]+2,255),fill='green')
        self.assertEqual(showdown_regions(im,1,0)[0].getpixel((0,0)),(255,0,0))
        self.assertEqual(showdown_regions(im,1,2)[0].tobytes(),regions(im,1,'board',2)[0].tobytes())
    def test_other_counts_rejected(self):
        for indices in ([],[0],[0,1],[0,1,2,3],[0,1,2,3,4]):
            self.assertIsNone(showdown_regions(sample(indices),1,0))
    def test_orange_animation_guard(self):
        im=sample([]);ImageDraw.Draw(im).rectangle((270,274,300,289),fill=(230,190,10))
        self.assertEqual(feature(im,1,'board',4),(None,None,None,False))
    def test_highlight_cache_bypassed(self):
        im=sample([0,1,4]);reader=CardReader(None,suprema_soft_bank={})
        with patch('plo5_suprema_soft.classify',return_value={'card':None}) as m:
            reader.suprema_slot(im,1,'board',0,{})
            reader.suprema_slot(im,1,'board',0,{})
            self.assertEqual(m.call_count,2)
    def test_normal_geometry(self):
        im=sample([])
        with patch('plo5_suprema_soft.soft_ink',return_value=(None,None)) as m:
            # Normal empty felt is detected before OCR; no change to existing guard.
            self.assertEqual(feature(im,1,'board',0),(None,None,None,True))
            m.assert_not_called()

if __name__=='__main__':unittest.main()
