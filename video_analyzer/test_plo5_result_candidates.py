import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image, ImageDraw, ImageFont
import plo5_result_candidates as r

PROFILE={'variant':5,'tables':[{'table_id':1,'seats':[{'seat':i+1,'result':[0,i*60,480,54]} for i in range(5)]}]}
REGIONS=[{'table_id':1,'x':0,'y':0,'width':480,'height':320}]


def row(p,text,*,table=1,seat=1,draft='a',status='result_label_candidate'):
    return {'table_id':table,'seat':seat,'pts':p,'file':f'{table}_{p}.jpg','draft_id':draft,
            'reading':{'candidate':r.parse_result(text),'status':status}}


def draft_fixture(binding,manifest):
    frames=[{'file':s['file'],'pts':s['actual_frame_timestamp_seconds'],'crop_sha256':s['sha256'],
             'hero_seat_declared':1,'actions':[{'seat':i} for i in range(1,6)]} for s in manifest['samples']]
    return {'job_id':binding['job_id'],'variant':5,'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'status':'unverified_hand_timeline_drafts',
            'hands_reconstructed':False,'actions_verified':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False,
            'drafts':[{'draft_id':'table_01_segment_0001','table_id':1,'hand_id':None,'complete_hand_verified':False,'frames':frames}], 'unassigned':[]}


class ResultTests(unittest.TestCase):
    def test_labels_and_pot_scope(self):
        for text,kind,pot,value in [('SHOWDOWN','showdown',None,None),('WIN MAIN 60 BB','payout','main','60'),
            ('GANHOU LATERAL 2 20,5 BB','payout','side_2','20.5'),('WIN 10 BB','payout',None,'10'),
            ('RETURN 5 BB','return',None,'5'),('REBUY 100 chips','rebuy',None,'100'),('TOP-UP','rebuy',None,None)]:
            v=r.parse_result(text)
            self.assertEqual((v['kind'],v['pot_id_candidate'],(v['displayed_amount'] or {}).get('value')),(kind,pot,value))
        self.assertEqual(r.parse_result('REBUY 100 chips')['displayed_amount']['unit'],'chips')

    def test_invalid_and_no_inference(self):
        for text in ('','120 BB','WINNER?','WIN 60','SHOWDOWN 5 BB','RETURN -5 BB','WIN 0 BB','WIN SIDE 6 10 BB','WIN 1,234 BB','REBUY 10 BB WIN 20 BB'):
            self.assertIsNone(r.parse_result(text),text)

    def test_persistent_labels_and_changes(self):
        out=r.episodes([row(0,'WIN MAIN 60 BB'),row(1,'WIN MAIN 60 BB'),row(2,'WIN SIDE 1 20 BB'),row(3,'REBUY 100 BB')])
        self.assertEqual(len(out),3); self.assertEqual(len(out[0]['evidence_files']),2)
        self.assertTrue(all(not x['financial_event_verified'] for x in out))

    def test_isolation_gaps_and_unassigned(self):
        out=r.episodes([row(0,'WIN'),row(1,'WIN',draft=None),row(2,'WIN'),row(3,'WIN',draft='b'),row(30,'WIN',draft='b'),row(0,'WIN',table=2),row(0,'REBUY',seat=2)])
        self.assertEqual(len(out),6)
        self.assertEqual(r.episodes([row(0,'WIN'),row(0,'REBUY')]),[])
        self.assertEqual(len(r.episodes([row(0,'WIN'),row(1,'WIN',status='uncertain_label'),row(2,'WIN')])),2)

    def test_profile_rejects_bad_variants_and_overlap(self):
        self.assertEqual(r.validate_profile(PROFILE,REGIONS)[1],PROFILE['tables'][0])
        bad=copy.deepcopy(PROFILE);bad['tables'][0]['seats'][1]['result']=bad['tables'][0]['seats'][0]['result']
        for p in (bad,dict(PROFILE,variant=6)):
            with self.assertRaises(ValueError):r.validate_profile(p,REGIONS)

    def test_draft_binding_rejects_mismatch(self):
        binding={'job_id':'a'*32,'source_sha256':'b'*64,'reports':{'evidence/ingest/manifest.json':'c'*64}}
        manifest={'source_sha256':'b'*64,'samples':[{'file':'table_01_sample_000.jpg','actual_frame_timestamp_seconds':1,'sha256':'d'*64,'table_id':1}]}
        d=draft_fixture(binding,manifest); tables=r.validate_profile(PROFILE,REGIONS)
        self.assertEqual(r.bind_drafts(binding,manifest,d,tables)['table_01_sample_000.jpg']['draft_id'],'table_01_segment_0001')
        for mutation in ('sha','seat','table','missing','duplicate','verified'):
            x=copy.deepcopy(d); f=x['drafts'][0]['frames'][0]
            if mutation=='sha': f['crop_sha256']='0'*64
            elif mutation=='seat': f['actions'].pop()
            elif mutation=='table': x['drafts'][0]['table_id']=2
            elif mutation=='missing': x['drafts'].clear()
            elif mutation=='duplicate': x['drafts'][0]['frames'].append(f)
            else: x['equity_ev_authorized']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):r.bind_drafts(binding,manifest,x,tables)

    @unittest.skipUnless(all(shutil.which(x) for x in ('ffmpeg','ffprobe','tesseract')),'Media/OCR required')
    def test_real_mp4_bound_result_labels(self):
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job, read_bound_evidence
        from offline_ingest_pts_audit import read_manifest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); image=Image.new('RGB',(480,320),'white');draw=ImageDraw.Draw(image)
            font=ImageFont.truetype('DejaVuSans.ttf',28)
            for s,text in zip(PROFILE['tables'][0]['seats'],('WIN MAIN 60 BB','WIN SIDE 1 20 BB','RETURN 5 BB','REBUY 100 BB','SHOWDOWN')):
                x,y,w,h=s['result'];draw.text((x+10,y+8),text,font=font,fill='black')
            image.save(root/'frame.png');video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'frame.png'),'-t','2','-r','5','-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=root/'regions.json';regions.write_text(json.dumps({'tables':REGIONS}))
            profile=root/'profile.json';profile.write_text(json.dumps(PROFILE))
            db=root/'jobs.db';job=ingest_local(video,root/'uploads',db)
            result=run_job(db,job['job_id'],regions,root/'out',pixel_checks=1)
            folder=Path(result['result_path']).parent/'evidence/ingest'
            binding=read_bound_evidence(db,job['job_id']); manifest=read_manifest(folder/'manifest.json')
            draft=root/'draft.json';draft.write_text(json.dumps(draft_fixture(binding,manifest)))
            with self.assertRaisesRegex(ValueError,'budget'):r.analyze_job(db,job['job_id'],draft,profile,max_tasks=1)
            report=r.analyze_job(db,job['job_id'],draft,profile,threshold=.70)
            self.assertEqual(len(report['observations']),15)
            self.assertEqual([(x['seat'],x['candidate']['kind'],x['candidate']['pot_id_candidate'],(x['candidate']['displayed_amount'] or {}).get('value'),len(x['evidence_files'])) for x in report['episodes']],
                 [(1,'payout','main','60',3),(2,'payout','side_1','20',3),(3,'return',None,'5',3),(4,'rebuy',None,'100',3),(5,'showdown',None,None,3)],report['observations'])
            self.assertIsNone(report['financial_result_bb']);self.assertFalse(report['winners_verified'])
            next(folder.glob('*.jpg')).write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):r.analyze_job(db,job['job_id'],draft,profile)


if __name__=='__main__':unittest.main()
