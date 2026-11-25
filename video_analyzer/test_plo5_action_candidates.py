import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image, ImageDraw, ImageFont
import plo5_action_candidates as a
from test_plo5_context_candidates import TABLE, REGIONS

PROFILE={'variant':5,'tables':[copy.deepcopy(TABLE)]}
for i,s in enumerate(PROFILE['tables'][0]['seats']):
    s['action']=[480,60+60*i,160,50]


def row(pts, label=None, *, table=1, seat=1, uncertain=False):
    return {'table_id':table,'seat':seat,'pts':pts,'file':f'{table}_{pts}.jpg',
            'reading':{'candidate':a.parse_action(label) if label else None,
                       'status':'uncertain_label' if uncertain else 'action_label_candidate' if label else 'uniform_blank_candidate'}}


class ActionTests(unittest.TestCase):
    def test_exact_labels_and_units(self):
        for text,expected in [('FOLD','fold'),('Desistiu','fold'),('CHECK','check'),('Passou','check'),('CALL','call'),('Pagar','call'),('BET','bet'),('Raise 3,5 BB','raise'),('ALL-IN','all_in'),('ALL IN 100 chips','all_in')]:
            self.assertEqual(a.parse_action(text)['action'],expected)
        self.assertEqual(a.parse_action('Raise 3,5 BB')['displayed_amount'],{'value':'3.5','unit':'BB'})
        for text in ('','folding','Call 3','fold 1 BB','raise 1,234 BB','bet 0 BB','call -1 BB','raise call','all-in?'):
            self.assertIsNone(a.parse_action(text))

    def test_persistent_labels_not_multiple_actions(self):
        out,duplicates=a.episodes([row(0),row(1,'fold'),row(2,'fold'),row(3,'fold')])
        self.assertEqual(duplicates,0)
        self.assertEqual(len(out),1)
        self.assertEqual((out[0]['first_seen_pts'],out[0]['last_seen_pts'],out[0]['observations']),(1,3,3))
        self.assertEqual(out[0]['onset_review_interval_pts'],[0,1])
        self.assertFalse(out[0]['distinct_poker_action_verified'])

    def test_uncertainty_duplicate_and_gap(self):
        for rows in ([row(0),row(1,uncertain=True),row(2,'call')],
                     [row(0),row(1,'fold'),row(1,'call'),row(2,'raise')],
                     [row(0),row(50,'bet')]):
            out,_=a.episodes(rows)
            self.assertEqual(len(out),1)
            self.assertIsNone(out[0]['onset_review_interval_pts'])
        self.assertEqual(a.episodes([row(1,'fold'),row(1,'call')]),([],2))

    def test_multi_table_actor_order_and_all_in(self):
        out,_=a.episodes([row(0,table=1),row(1,'raise'),row(2,'all-in'),row(1,'fold',seat=2),row(1,'call',table=2)])
        self.assertEqual([(r['table_id'],r['seat'],r['action']) for r in out],[(1,1,'raise'),(1,2,'fold'),(1,1,'all_in'),(2,1,'call')])
        self.assertTrue(all(not r['order_verified'] for r in out))

    def test_profile_and_overlaps(self):
        self.assertEqual(a.validate_profile(PROFILE,REGIONS)[1],PROFILE['tables'][0])
        for field in ('stack','action'):
            bad=copy.deepcopy(PROFILE); bad['tables'][0]['seats'][0]['action']=bad['tables'][0]['seats'][1][field]
            with self.assertRaises(ValueError):
                a.validate_profile(bad,REGIONS)
        with self.assertRaises(ValueError):
            a.validate_profile(dict(PROFILE,variant=6),REGIONS)

    def test_blank_ocr_bypassed(self):
        from unittest.mock import patch
        with patch('plo5_action_candidates.read_roi') as reader:
            reading=a.read_action(Image.new('RGB',(32,32),'white'),[0,0,32,32],.75)
        reader.assert_not_called()
        self.assertEqual(reading['status'],'uniform_blank_candidate')
        self.assertIsNone(reading['candidate'])

    @unittest.skipUnless(all(shutil.which(x) for x in ('ffmpeg','ffprobe','tesseract')),'Media/OCR tools required')
    def test_mp4_bound_action_and_money(self):
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); im=Image.new('RGB',(640,240),'white'); draw=ImageDraw.Draw(im)
            font=ImageFont.truetype('DejaVuSans.ttf',26)
            t=PROFILE['tables'][0]
            fields=[(t['pot'],'10 BB'),(t['blinds'],'0.5/1 BB')]
            for s,stack,bet,label in zip(t['seats'],('120 BB','70 BB'),('3 BB','1 BB'),('FOLD','CALL')):
                fields.extend((s[k],v) for k,v in [('stack',stack),('bet',bet),('action',label)])
            for rect,label in fields:
                draw.text((rect[0]+8,rect[1]+8),label,font=font,fill='black')
            im.save(root/'frame.png'); video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'frame.png'),'-t','2','-r','5','-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=root/'regions.json';regions.write_text(json.dumps({'tables':REGIONS}))
            profile=root/'profile.json';profile.write_text(json.dumps(PROFILE))
            db=root/'jobs.db'; job=ingest_local(video,root/'uploads',db)
            result=run_job(db,job['job_id'],regions,root/'out',pixel_checks=1)
            with self.assertRaisesRegex(ValueError,'budget'):
                a.analyze_job(db,job['job_id'],profile,max_tasks=1)
            report=a.analyze_job(db,job['job_id'],profile,threshold=.70)
            self.assertEqual(len(report['observations']),6)
            self.assertEqual(report['roi_tasks'],24)
            self.assertEqual([(r['seat'],r['action'],r['observations']) for r in report['episodes']],[(1,'fold',3),(2,'call',3)])
            for r in report['observations']:
                ctx=r['same_frame_context'];self.assertEqual(ctx['pot_bb'],'10',r)
                self.assertEqual(ctx['remaining_stack_bb'],'120' if r['seat']==1 else '70',r)
                self.assertEqual(ctx['visible_bet_bb'],'3' if r['seat']==1 else '1',r)
                self.assertIsNone(ctx['amount_to_call_bb'])
            self.assertFalse(report['actions_verified']); self.assertFalse(report['equity_ev_authorized'])
            crop=next((Path(result['result_path']).parent/'evidence/ingest').glob('*.jpg'));crop.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):
                a.analyze_job(db,job['job_id'],profile)


if __name__=='__main__':
    unittest.main()
