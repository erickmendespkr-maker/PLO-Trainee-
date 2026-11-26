import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from plo5_fourcolor_cards import ink,signature,distance,train,classify,observe,load_bank,RANKS

class CardTests(unittest.TestCase):
    def test_colors_and_dim(self):
        for factor in (1,.55):
            for suit,rgb in [('c',(0,125,0)),('h',(230,0,0)),('s',(0,0,0)),('d',(0,70,220))]:
                im=Image.new('RGB',(12,16),(int(240*factor),)*3)
                ImageDraw.Draw(im).rectangle((3,3,7,12),fill=tuple(int(c*factor) for c in rgb))
                self.assertEqual(ink(im)[0],suit)
    def test_mask(self):
        m=[False]*16
        for i in [5,6,9,10]:m[i]=True
        g,a=signature(m,(4,4));self.assertEqual((len(g),a),(480,1));self.assertEqual(distance(g,g),0)
    def test_ambiguous_color_rejected(self):
        with patch('plo5_fourcolor_cards.feature',return_value=('c','h',(b'\xff'*480,1),.8,.8,False)):
            self.assertIsNone(classify(None,1,'hero',0,{} )['card'])
    def test_tied_rank_rejected(self):
        g=b'\xff'*480
        with patch('plo5_fourcolor_cards.feature',return_value=('d','d',(g,1),.8,.8,False)):
            self.assertIsNone(classify(None,1,'hero',0,{'A':[(g,1,'hero')],'K':[(g,1,'hero')]})['card'])
    def test_empty_and_unsupported(self):
        im=Image.new('RGB',(1504,696),(30,110,80))
        self.assertEqual(classify(im,1,'board',0,{})['status'],'felt_empty_candidate')
        with patch('plo5_fourcolor_cards.detect',return_value='suprema'):
            self.assertIsNone(observe(im,1,{})['hero_cards'])
    def test_duplicate_and_collision(self):
        im=Image.new('RGB',(1504,696))
        def fake(image,t,f,i,bank):
            cards=['Ac','Kd','Qh','Js','Tc'] if f=='hero' else ['Ac','2h','3s',None,None]
            return {'card':cards[i],'status':'candidate_unverified' if cards[i] else 'felt_empty_candidate'}
        with patch('plo5_fourcolor_cards.detect',return_value='pppoker'),patch('plo5_fourcolor_cards.classify',side_effect=fake):
            r=observe(im,1,{});self.assertIsNone(r['hero_cards']);self.assertIsNone(r['board_cards']);self.assertFalse(r['cards_verified'])
    def test_missing_training_classes(self):
        with self.assertRaisesRegex(ValueError,'Missing rank'):train([])
    def test_bank_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bank.json';p.write_text(json.dumps({r:[['ff'*480,1,'hero']] for r in RANKS}));self.assertEqual(len(load_bank(p)),13)
            p.write_text('{}')
            with self.assertRaises(ValueError):load_bank(p)
if __name__=='__main__':unittest.main()
