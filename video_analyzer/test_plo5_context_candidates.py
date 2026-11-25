import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image, ImageDraw, ImageFont
import plo5_context_candidates as c

TABLE={'table_id':1,'hero_seat':1,'pot':[0,0,180,50],'blinds':[200,0,200,50],
       'seats':[{'seat':1,'stack':[0,60,180,50],'bet':[200,60,180,50],'dealer':[400,60,80,50]},
                {'seat':2,'stack':[0,120,180,50],'bet':[200,120,180,50],'dealer':[400,120,80,50]}]}
PROFILE={'variant':5,'tables':[TABLE]}
REGIONS=[{'table_id':1,'x':0,'y':0,'width':640,'height':240}]


def reading(value=None, raw=''):
    return {'candidate':value,'raw':raw,'uniform_blank_candidate':not raw and value is None}


class ContextTests(unittest.TestCase):
    def test_units_and_ambiguity(self):
        self.assertEqual(c.parse_amount('12,50 BB'),{'value':'12.5','unit':'BB'})
        self.assertEqual(c.parse_amount('0 fichas'),{'value':'0','unit':'chips'})
        for text in ('','12','1,234 BB','1.234 BB','-2 BB','NaN BB','10 BB 20','R$ 10','2e3 BB'):
            self.assertIsNone(c.parse_amount(text))

    def test_blinds_and_conversion(self):
        b=c.parse_blinds('50/100 chips')
        self.assertEqual(c.as_bb(c.parse_amount('1250 chips'),b),'12.5')
        self.assertEqual(c.as_bb(c.parse_amount('9 BB'),None),'9')
        self.assertIsNone(c.as_bb(c.parse_amount('1250 chips'),c.parse_blinds('0.5/1 BB')))
        for text in ('0/100 chips','100/50 chips','50/100','1/2 BB','0.5/1.000 BB'):
            self.assertIsNone(c.parse_blinds(text))

    def test_position_map(self):
        self.assertEqual(c.position_map([1,2,3,4,5,6],4),{4:'BTN',5:'SB',6:'BB',1:'EP',2:'MP',3:'CO'})
        self.assertEqual(c.position_map([1,2],2),{2:'BTN/SB',1:'BB'})
        self.assertIsNone(c.position_map([1,2],3))
        for n in (3,4,5):
            self.assertEqual(len(c.position_map(list(range(1,n+1)),1)),n)

    def test_pairwise_remaining_and_unknowns(self):
        seats=[{'seat':1,'stack':reading(c.parse_amount('120 BB')),'bet':reading(c.parse_amount('3 BB')),'dealer':reading('dealer_marker','D')},
               {'seat':2,'stack':reading(c.parse_amount('70 BB')),'bet':reading(),'dealer':reading()}]
        r=c.derive(TABLE,reading(c.parse_amount('10 BB')),reading(),seats)
        self.assertEqual(r['hero_position_candidate'],'BTN/SB')
        self.assertEqual(r['pairwise_remaining_effective_bb'],[{'opponent_seat':2,'remaining_effective_bb':'70'}])
        self.assertIsNone(r['visible_bets_bb'][2])
        self.assertIsNone(r['initial_effective_stack_bb'])
        self.assertIsNone(r['amount_to_call_bb'])
        seats[1]['dealer']=reading('dealer_marker','D')
        self.assertIsNone(c.derive(TABLE,reading(),reading(),seats)['positions_candidate'])
        seats[1]['dealer']=reading(None,'?')
        seats[1]['stack']=reading(c.parse_amount('700 chips'))
        r=c.derive(TABLE,reading(),reading(),seats)
        self.assertIsNone(r['positions_candidate'])
        self.assertIsNone(r['pairwise_remaining_effective_bb'][0]['remaining_effective_bb'])

    def test_blank_dealer_roi(self):
        from unittest.mock import patch
        with patch('plo5_context_candidates.subprocess.run') as proc:
            result=c.read_roi(Image.new('RGB',(32,32),'white'),[0,0,32,32],'dealer',.75)
        proc.assert_not_called()
        self.assertTrue(result['uniform_blank_candidate'])
        self.assertIsNone(result['candidate'])

    def test_profile_rejects_bad_variant_and_overlaps(self):
        self.assertEqual(c.validate_profile(PROFILE,REGIONS)[1],TABLE)
        for t in (dict(TABLE,pot=TABLE['blinds']),dict(TABLE,hero_seat=3),dict(TABLE,seats=[TABLE['seats'][0]]*2)):
            with self.assertRaises(ValueError):
                c.validate_profile(dict(PROFILE,tables=[t]),REGIONS)
        with self.assertRaises(ValueError):
            c.validate_profile(dict(PROFILE,variant=6),REGIONS)

    @unittest.skipUnless(all(shutil.which(x) for x in ('ffmpeg','ffprobe','tesseract')),'Media/OCR tools required')
    def test_real_mp4_ocr_and_binding(self):
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); im=Image.new('RGB',(640,240),'white'); draw=ImageDraw.Draw(im)
            font=ImageFont.truetype('DejaVuSans.ttf',26)
            fields=[(TABLE['pot'],'10 BB'),(TABLE['blinds'],'0.5/1 BB')]
            for seat,stack,bet,marker in zip(TABLE['seats'],('120 BB','70 BB'),('3 BB','1 BB'),('D','')):
                fields.extend((seat[k],v) for k,v in [('stack',stack),('bet',bet),('dealer',marker)])
            for rect,text in fields:
                draw.text((rect[0]+8,rect[1]+8),text,font=font,fill='black')
            im.save(root/'frame.png'); video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'frame.png'),'-t','2','-r','5','-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=root/'regions.json';regions.write_text(json.dumps({'tables':REGIONS}))
            profile=root/'profile.json';profile.write_text(json.dumps(PROFILE))
            db=root/'jobs.db'; job=ingest_local(video,root/'uploads',db)
            result=run_job(db,job['job_id'],regions,root/'out',pixel_checks=1)
            with self.assertRaisesRegex(ValueError,'budget'):
                c.analyze_job(db,job['job_id'],profile,max_tasks=1)
            report=c.analyze_job(db,job['job_id'],profile,threshold=.70)
            self.assertEqual(report['ocr_tasks'],24)
            self.assertEqual(len(report['observations']),3)
            for row in report['observations']:
                d=row['derived_candidates']
                self.assertEqual(d['pot_bb'],'10',row)
                self.assertEqual(row['blinds']['candidate'],{'sb':'0.5','bb':'1','unit':'BB'},row)
                self.assertEqual(d['remaining_stacks_bb'],{1:'120',2:'70'},row)
                self.assertEqual(d['visible_bets_bb'],{1:'3',2:'1'},row)
                self.assertEqual(d['hero_position_candidate'],'BTN/SB',row)
                self.assertEqual(d['pairwise_remaining_effective_bb'][0]['remaining_effective_bb'],'70')
            self.assertFalse(report['equity_ev_authorized'])
            crop=next((Path(result['result_path']).parent/'evidence/ingest').glob('*.jpg'));crop.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):
                c.analyze_job(db,job['job_id'],profile)


if __name__=='__main__':
    unittest.main()
