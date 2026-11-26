import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_fourcolor_cards import RANKS
from plo5_suprema_soft import soft_ink, feature, classify, load_bank, train, PROFILE
from plo5_event_card_consensus import run

class SoftInkTests(unittest.TestCase):
    def test_brightness_relative_colors(self):
        for v in (1,.35):
            for s,color in [('c',(0,125,0)),('h',(210,0,0)),('d',(0,65,210)),('s',(0,0,0))]:
                im=Image.new('RGB',(20,24),(int(240*v),)*3)
                ImageDraw.Draw(im).rectangle((5,6,10,17),fill=tuple(int(x*v) for x in color))
                suit,sig=soft_ink(im);self.assertEqual(suit,s);self.assertEqual(len(sig[0]),480)
    def test_blue_felt(self):
        self.assertEqual(soft_ink(Image.new('RGB',(20,24),(30,48,80))),(None,None))
    def test_highlight(self):
        im=Image.new('RGB',(1504,696),(30,48,80));ImageDraw.Draw(im).rectangle((65,248,70,290),fill=(220,180,10))
        self.assertEqual(feature(im,1,'board',0),(None,None,None,False))
    def test_tied_rank(self):
        g=b'\xff'*480
        with patch('plo5_suprema_soft.feature',return_value=('d','d',(g,1),False)):
            self.assertIsNone(classify(None,1,'hero',0,{'A':[(g,1,'hero')],'K':[(g,1,'hero')]})['card'])
    def test_color_disagreement(self):
        with patch('plo5_suprema_soft.feature',return_value=('c','d',(b'\xff'*480,1),False)):
            self.assertIsNone(classify(None,1,'hero',0,{})['card'])
    def test_wrong_bank(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bank.json';rows={r:[['ff'*480,1,'hero']] for r in RANKS};p.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError,'Wrong Suprema'):load_bank(p)
            p.write_text(json.dumps({'profile':PROFILE,'templates':rows}));self.assertEqual(len(load_bank(p)),13)
    def test_missing_templates(self):
        with self.assertRaisesRegex(ValueError,'Missing rank'):train([])
    def test_conflicting_banks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'manifest.json').write_text(json.dumps({'variant':5,'status':'PIXEL_CHANGE_CANDIDATES_ONLY','sampling_hz':8}))
            with self.assertRaisesRegex(ValueError,'conflicting'):run(p,{'suprema':'a','suprema_soft':'b'})
    def test_route(self):
        from plo5_review_pipeline import main
        with patch('plo5_event_card_consensus.main',return_value=0) as m:
            self.assertEqual(main(['event-cards','folder','output']),0);m.assert_called_once_with(['folder','output'])

if __name__=='__main__':unittest.main()
