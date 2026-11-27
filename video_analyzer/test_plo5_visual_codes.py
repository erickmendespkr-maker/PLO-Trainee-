import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from plo5_visual_codes import Codebook,LayoutCache,RegionReader,MixedReader,code,pixels,labeled_row,VERSION
from plo5_mixed_money import STARTS,REGIONS,detect
import json


def frame(platforms):
    im=Image.new('RGB',(1504,696),(0,0,0));d=ImageDraw.Draw(im)
    for x,p in zip(STARTS,platforms):
        if p is None:continue
        d.rectangle((x,0,x+371,695),fill=(30,110,45) if p=='pppoker' else (30,50,95))
        d.rectangle((x+120,5,x+244,21),fill=(10,10,10) if p=='pppoker' else (250,250,250))
        for f,(a,b,c,e) in REGIONS[p].items():
            d.rectangle((x+a,b,x+c-1,e-1),fill=(10,10,10));d.text((x+a,b),'100 BB',fill='white')
    return im


class VisualCodesTests(unittest.TestCase):
    def test_layout_changes_and_reference(self):
        c=LayoutCache();states=[['pppoker','suprema','pppoker','suprema'],['pppoker',None,'pppoker','suprema'],[None,None,'suprema',None]]
        for s in states+states:
            im=frame(s);self.assertEqual(c.scan(im),s);self.assertEqual(c.scan(im),[detect(im,t) for t in range(1,5)])
        self.assertGreater(c.stats()['hits'],c.stats()['misses'])
        with self.assertRaises(ValueError):c.scan(Image.new('RGB',(100,100)))
    def test_exact_conflicts_and_namespace(self):
        im=Image.new('RGB',(10,10));r=(0,0,5,5);row=labeled_row('p','stack',im,r,'100 BB');p=pixels(im,r)
        b=Codebook([row,row]);self.assertEqual(b.match('p','stack',p)['label'],'100 BB')
        self.assertEqual(b.match('p','pot',p)['status'],'UNKNOWN')
        b=Codebook([row,dict(row,label='10 BB')]);self.assertEqual(b.match('p','stack',p)['status'],'CONFLICT')
        im.putpixel((1,1),(0,0,1));self.assertNotEqual(code('p','stack',p),code('p','stack',pixels(im,r)))
    def test_reader_cache_and_abstention(self):
        im=Image.new('RGB',(20,20));r=(0,0,5,5);reader=RegionReader();calls=[]
        def decoder(x):calls.append(x.tobytes());return None
        for _ in range(10):self.assertIsNone(reader.read('p','action',im,r,decoder)['label'])
        im.putpixel((19,19),(1,0,0));reader.read('p','action',im,r,decoder);self.assertEqual(len(calls),1)
        im.putpixel((1,1),(1,0,0));reader.read('p','action',im,r,decoder);self.assertEqual(len(calls),2)
        reader.read('p','stack',im,r,decoder);self.assertEqual(len(calls),3)
    def test_bank_file_and_limits(self):
        im=Image.new('RGB',(10,10));row=labeled_row('p','rank',im,(0,0,5,5),'A')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bank.json';p.write_text(json.dumps(dict(version=VERSION,rows=[row])))
            self.assertEqual(Codebook.load(p).match('p','rank',pixels(im,(0,0,5,5)))['label'],'A')
        with self.assertRaises(ValueError):Codebook([dict(row,hex='00')])
        with self.assertRaises(ValueError):pixels(im,(-1,0,5,5))
    def test_mixed_reader_manual_and_fallback(self):
        im=frame(['pppoker','pppoker',None,'suprema']);a,b,c,d=REGIONS['pppoker']['stack']
        row=labeled_row('pppoker-1504x696-money-v1','stack',im,(a,b,c,d),'100.00 BB','L')
        with patch('plo5_mixed_money.read',return_value=dict(value_bb='7',raw='7 BB',confidence=.9)) as fallback:
            reader=MixedReader(bank=Codebook([row]));rows=reader.scan(im);self.assertEqual(len(rows),8)
            self.assertEqual(rows[0]['value_bb'],'100');self.assertEqual(rows[2]['source'],'MANUAL_CODE')
            self.assertEqual(rows[4]['source'],'NO_LAYOUT');self.assertEqual(fallback.call_count,3)
            self.assertEqual(rows,reader.scan(im));self.assertEqual(fallback.call_count,3)
            im.putpixel((a,b),(255,255,255));self.assertEqual(reader.scan(im)[0]['source'],'OCR_FALLBACK');self.assertEqual(fallback.call_count,4)
    def test_conflict_no_ocr(self):
        im=frame(['pppoker',None,None,None]);a,b,c,d=REGIONS['pppoker']['stack'];row=labeled_row('pppoker-1504x696-money-v1','stack',im,(a,b,c,d),'100.00 BB','L')
        with patch('plo5_mixed_money.read',return_value=dict(value_bb=None,raw='',confidence=None)) as fallback:
            r=MixedReader(bank=Codebook([row,dict(row,label='10.00 BB')])).scan(im)
            self.assertEqual(r[0]['source'],'CONFLICT');self.assertIsNone(r[0]['value_bb']);self.assertEqual(fallback.call_count,1)

if __name__=='__main__':unittest.main()
