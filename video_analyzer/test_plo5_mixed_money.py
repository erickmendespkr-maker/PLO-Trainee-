import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_mixed_money import detect, parse, read, scan, STARTS


def fixture():
    im=Image.new('RGB',(1504,696),(15,60,100));d=ImageDraw.Draw(im)
    for i,x in enumerate(STARTS[:2]):
        d.rectangle((x,0,x+371,695),fill=(30,110,80) if i==0 else (32,48,80))
        d.rectangle((x,0,x+371,29),fill=(35,36,41) if i==0 else (255,255,255))
    return im


class MixedMoneyTests(unittest.TestCase):
    def test_decimal(self):
        self.assertEqual(parse('Pot: 139,0 BB','pppoker','pot'),'139')
        self.assertEqual(parse('99.5 BB','suprema','stack'),'99.5')
        self.assertEqual(parse('100 BB','suprema','stack'),'100')
    def test_reject_bad_text(self):
        for raw in ('Caça ao Coelho','15 chips','15 BB','Pot: 1,2,3 BB','Pot: -3 BB','Pot: 1.234 BB'):
            self.assertIsNone(parse(raw,'pppoker','pot'))
        self.assertIsNone(parse('995 BB','pppoker','stack'))
    def test_layout(self):
        im=fixture();self.assertEqual([detect(im,i) for i in range(1,5)],['pppoker','suprema',None,None])
    def test_wrong_header(self):
        im=fixture();ImageDraw.Draw(im).rectangle((0,0,371,29),fill='white');self.assertIsNone(detect(im,1))
    def test_blank_and_geometry(self):
        self.assertIsNone(read(fixture(),1,'pppoker','stack')['value_bb'])
        with self.assertRaises(ValueError):detect(Image.new('RGB',(800,600)),1)
        with self.assertRaises(ValueError):read(fixture(),5,'pppoker','stack')
    def test_scan_skips_inactive(self):
        with patch('plo5_mixed_money.read',return_value={'value_bb':'1','raw':'1 BB','confidence':.9}) as mock:
            r=scan(fixture());self.assertEqual(mock.call_count,4);self.assertEqual(len(r),8)
            self.assertEqual(sum(x['layout_candidate_active'] for x in r),4);self.assertTrue(all(not x['financial_result_verified'] for x in r))
    def test_declared_mismatch(self):
        with patch('plo5_mixed_money.read') as mock:
            r=scan(fixture(),['suprema','pppoker','pppoker','suprema']);mock.assert_not_called()
            self.assertTrue(all(x['value_bb'] is None for x in r))
    def test_invalid_settings(self):
        with self.assertRaises(ValueError):scan(fixture(),['pppoker'])
        with self.assertRaises(ValueError):scan(fixture(),workers=4)

if __name__=='__main__':unittest.main()
