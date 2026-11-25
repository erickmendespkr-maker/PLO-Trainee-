import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageEnhance
import plo5_visual_calibration as v


class VisualCalibrationTests(unittest.TestCase):
    def test_two_layouts_and_presence(self):
        for size in v.LAYOUTS:
            im=Image.new('RGB',size,(28,43,68))
            self.assertIs(v.present(im),True)
            self.assertIs(v.present(Image.new('RGB',size,'black')),False)
            for field in ('hero','board'):
                for i in range(5):self.assertEqual(v.slot(im,field,i)[0],'empty')
            out=v.observe(im,{'rank':{},'suit':{}})
            self.assertEqual(out['board_cards'],[]);self.assertIsNone(out['hero_cards']);self.assertFalse(out['cards_verified'])
        with self.assertRaises(ValueError):v.observe(Image.new('RGB',(100,100)),{})

    def test_relative_contrast_dimmed_glyph_and_color(self):
        im=Image.new('RGB',(24,24),(235,235,235));d=ImageDraw.Draw(im);d.rectangle((9,3,14,20),fill=(5,5,5));d.rectangle((5,3,14,7),fill=(5,5,5))
        self.assertIsNotNone(v.signature(im));self.assertEqual(v.signature(im),v.signature(ImageEnhance.Brightness(im).enhance(.35)))
        self.assertIsNone(v.signature(Image.new('RGB',(24,24),(50,50,50))))
        for rgb,s in [((160,20,20),'h'),((10,125,30),'c'),((12,45,160),'d'),((10,10,10),'s')]:
            a=Image.new('RGB',(12,12),(230,230,230));ImageDraw.Draw(a).rectangle((3,3,8,9),fill=rgb)
            self.assertEqual(v.color(a),s)

    def test_ambiguous_matches_and_color_conflict(self):
        a=bytes([1,1,0,0]);b=bytes([0,0,1,1]);self.assertIsNone(v.nearest(a,{'A':[a],'K':[a]}));self.assertEqual(v.nearest(a,{'A':[a],'K':[b]}),'A')
        bank={'rank':{'A':[a],'K':[b]},'suit':{'h':[a],'c':[b]}};im=Image.new('RGB',(402,748),(28,43,68))
        with patch.object(v,'slot',return_value=('face',a,a,'c')):
            r=v.observe(im,bank);self.assertIsNone(r['hero_cards']);self.assertIsNone(r['board_cards']);self.assertTrue(all(s['card'] is None for s in r['hero_slots']))
        with patch.object(v,'slot',return_value=('face',a,a,'h')):
            r=v.observe(im,bank);self.assertTrue(r['duplicate_conflict']);self.assertIsNone(r['hero_cards']);self.assertIsNone(r['board_cards'])

    def test_train_requires_five_and_no_duplicates(self):
        im=Image.new('RGB',(402,748))
        for labels in (['As']*5,['As','Kd','Qc','Jh'],['As','Kd','Qc','Jh','Zs']):
            with self.assertRaises(ValueError):v.train([(im,{'hero':labels})])
        with self.assertRaises(ValueError):v.train([(Image.new('RGB',(10,10)),{'board':[]})])

    def test_crop_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'crop.jpg';Image.new('RGB',(402,748)).save(p);s={'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertEqual(v.checked_image(p.parent,s).size,(402,748));p.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'Crop changed'):v.checked_image(p.parent,s)

    def test_ocr_requires_explicit_bb_and_confidence(self):
        im=Image.new('RGB',(432,800));fake=type('Result',(),{'stdout':b'fake'})()
        with patch.object(v.subprocess,'run',return_value=fake),patch('ocr_probe.parse_tesseract_tsv',return_value=('123.5 BB',2,.95)):
            self.assertEqual(v.read_money(im,'stack')['candidate'],{'value':'123.5','unit':'BB'})
        for text,conf in [('123.5 BB',.5),('123.5',.99),('123.5 chips',.99)]:
            with patch.object(v.subprocess,'run',return_value=fake),patch('ocr_probe.parse_tesseract_tsv',return_value=(text,2,conf)):
                self.assertIsNone(v.read_money(im,'stack')['candidate'])

    def test_annotation_binding_partition_and_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);samples=[]
            for i in range(2):
                p=root/f'{i}.jpg';Image.new('RGB',(402,748),(28+i,43,68)).save(p);samples.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'actual_frame_timestamp_seconds':i,'table_id':1})
            b={'job_id':'a'*32,'source_sha256':'b'*64,'reports':{'evidence/ingest/manifest.json':'c'*64}};m={'samples':samples}
            ann={'variant':5,'job_id':b['job_id'],'source_sha256':b['source_sha256'],'manifest_sha256':'c'*64,'reference_kind':'synthetic_fixture','rows':[{'file':s['file'],'sha256':s['sha256'],'partition':p,'truth':{'visible':True}} for s,p in zip(samples,['train','holdout'])]}
            path=root/'ann.json';spec=[{'database':'fixture','job_id':b['job_id'],'annotations':str(path)}]
            for kind in ('variant','hash','order','cross_cards','hidden','duplicate','leak'):
                a=copy.deepcopy(ann);ms=copy.deepcopy(m)
                if kind=='variant':a['variant']=6
                elif kind=='hash':a['rows'][0]['sha256']='0'*64
                elif kind=='order':a['rows'][0]['partition'],a['rows'][1]['partition']='holdout','train'
                elif kind=='cross_cards':a['rows'][0]['truth'].update(hero='As Ks Qs Js Ts'.split(),board='As 2s 3s'.split())
                elif kind=='hidden':a['rows'][0]['truth'].update(visible=False,board=[])
                elif kind=='duplicate':a['rows'][1]=copy.deepcopy(a['rows'][0])
                else:ms['samples'][1]['sha256']=ms['samples'][0]['sha256'];a['rows'][1]['sha256']=a['rows'][0]['sha256']
                path.write_text(json.dumps(a))
                with patch.object(v,'load_job',return_value=(b,root,ms)),self.subTest(kind=kind),self.assertRaises(ValueError):v.evaluate_jobs(spec,root/'out.json')
                self.assertFalse((root/'out.json').exists())


if __name__=='__main__':unittest.main()
