import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from plo5_blind_evidence import Reader,compare,chip_present,REGIONS


def group():
    return {'table_id':1,'platform':'pppoker','positions_if_standard_blinds_and_full_roster':{'top':'SB','upper_right':'BB','hero_bottom':'BTN'}}


def observation(a='0.5',b='1',other=None):
    return {'table_id':1,'platform':'pppoker','stakes':[{'seat':'top','value_bb':a},{'seat':'upper_right','value_bb':b},{'seat':'hero_bottom','value_bb':other}]}


class BlindTests(unittest.TestCase):
    def test_compatible_not_verified(self):
        r=compare(group(),observation(),'1.5');self.assertEqual(r['status'],'STANDARD_BLIND_AMOUNTS_COMPATIBLE_CANDIDATE');self.assertFalse(r['blinds_verified']);self.assertFalse(r['positions_verified']);self.assertFalse(r['strategy_authorized'])
    def test_extra_or_missing(self):
        for obs,pot in ((observation(other='2'),'1.5'),(observation(a=None),'1.5'),(observation(),None),(observation(),'3.5')):
            self.assertEqual(compare(group(),obs,pot)['status'],'INCONCLUSIVE_OR_OTHER_ACTION')
    def test_mismatch(self):
        r=observation();r['table_id']=2
        with self.assertRaises(ValueError):compare(group(),r,'1.5')
    def test_no_chip_no_ocr(self):
        with patch('plo5_blind_evidence.detect',return_value='pppoker'),patch('plo5_blind_evidence.read_text') as m:
            r=Reader().scan(Image.new('RGB',(1504,696),(20,70,40)),1);self.assertEqual(len(r['stakes']),6);m.assert_not_called();self.assertTrue(all(q['value_bb'] is None for q in r['stakes']))
    def test_cache(self):
        im=Image.new('RGB',(1504,696),(20,70,40));_,(x,y)=REGIONS['pppoker']['top'];ImageDraw.Draw(im).rectangle((x-4,y-4,x+4,y+4),fill=(255,0,0));r=Reader()
        with patch('plo5_blind_evidence.detect',return_value='pppoker'),patch('plo5_blind_evidence.read_text',return_value={'raw':'0,5 BB','confidence':.9,'value_bb':'0.5'}) as m:
            self.assertEqual(r.scan(im,1),r.scan(im,1));self.assertEqual(m.call_count,1)
    def test_suprema_only_calibrated_seats(self):
        with patch('plo5_blind_evidence.detect',return_value='suprema'):
            r=Reader().scan(Image.new('RGB',(1504,696)),1);self.assertEqual({q['seat'] for q in r['stakes']},{'upper_left','lower_left'});self.assertFalse(r['all_stakes_verified'])
    def test_route(self):
        from plo5_review_pipeline import main
        with patch('plo5_blind_evidence.main',return_value=0) as m:
            self.assertEqual(main(['blind-evidence','report','out.json']),0);m.assert_called_once_with(['report','out.json'])
if __name__=='__main__':unittest.main()
