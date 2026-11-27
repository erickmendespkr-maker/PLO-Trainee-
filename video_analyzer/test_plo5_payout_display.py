import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_payout_display import parse, mask, Reader, episodes, REGIONS


def frame(t,value=None,flag=True):
    rows=[{'seat':s,'yellow_display_candidate':flag and s=='top','displayed_plus_bb':value if s=='top' else None,'raw':''} for s in REGIONS]
    return {'file':str(t)+'.png','pts':str(t),'sha256':'0'*64,'tables':{'1':rows,'2':[],'3':[],'4':[]}}


class PayoutDisplayTests(unittest.TestCase):
    def test_strict_amount(self):
        self.assertEqual(parse('+27,2 BB'),'27.2');self.assertEqual(parse('+9.0 BB'),'9')
        for x in ('27,2 BB','+272 BB','+27,2 BG','+0,0 BB','+27,2 BB extra'):
            self.assertIsNone(parse(x))
    def test_color_guard(self):
        im=Image.new('RGB',(100,24),'green');self.assertIsNone(mask(im));ImageDraw.Draw(im).rectangle((10,5,60,10),fill=(235,215,20));self.assertIsNotNone(mask(im))
    def test_unknown_platform(self):
        with patch('plo5_payout_display.detect',return_value='suprema'):self.assertEqual(Reader().scan(None,1),[])
    def test_no_color_no_ocr(self):
        with patch('plo5_payout_display.detect',return_value='pppoker'),patch('plo5_payout_display.ocr') as m:
            rows=Reader().scan(Image.new('RGB',(1504,696)),1);m.assert_not_called();self.assertEqual(len(rows),6);self.assertFalse(any(r['yellow_display_candidate'] for r in rows))
    def test_repeated_not_verified(self):
        r=episodes([frame(1,'9'),frame(2,'9')])[0];self.assertEqual(r['repeated_displayed_plus_bb_candidate'],'9');self.assertFalse(r['payout_verified']);self.assertFalse(r['winner_verified'])
    def test_conflicts_and_unknown(self):
        for values in (['9',None,'9'],['9','9','10'],[None,None]):
            r=episodes([frame(i,v) for i,v in enumerate(values,1)])[0];self.assertIsNone(r['repeated_displayed_plus_bb_candidate'])
    def test_gaps_and_absence(self):
        self.assertEqual(len(episodes([frame(1,'9'),frame(3,'9')])),2)
        self.assertEqual(len(episodes([frame(1,'9'),frame(2,flag=False),frame(3,'9')])),2)
        with self.assertRaises(ValueError):episodes([frame(1),frame(1)])
if __name__=='__main__':unittest.main()
