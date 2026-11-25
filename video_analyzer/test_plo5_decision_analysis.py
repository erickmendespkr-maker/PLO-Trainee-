import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

import plo5_decision_analysis as d
from test_plo5_action_ev import scenario


def fixture(preflop=False):
    s=scenario()
    if preflop:
        s.update(hero=['Ac','Ad','Ah','As','Ks'],board=[])
    context={'schema':'plo-decision-v2','players':2,'position':'SB',
             'street':'preflop' if preflop else 'river','hero':s['hero'],'board':s['board'],
             'amount_unit':'chips','bb_size':10,'stack':300,'pot':100,'to_call':20,
             'rake_percent':5,'rake_cap':10,'frequency_unit':'fraction','ev_baseline':'decision',
             'model':'reviewed fixture','node':'fixture node'}
    ident={'job_id':'a'*32,'variant':5,'source_sha256':'b'*64,'manifest_sha256':'c'*64}
    binding={**ident,'reports':{'evidence/ingest/manifest.json':'c'*64}}
    frames=[]; samples=[]
    for i in range(2):
        f={'file':f'f{i}.jpg','pts':i,'crop_sha256':f'{i:064x}','visible':True,
           'hero_seat_declared':1,'hero_cards':s['hero'],'board':s['board'],
           'context':{'hero_position_candidate':'BTN/SB','pot_bb':'10','remaining_stacks_bb':{'1':'30','2':'30'}},
           'actions':[{'seat':1,'reading':{'candidate':{'action':'call'} if i else None}},
                      {'seat':2,'reading':{'candidate':None}}],
           'hero_fold_label':False,'after_hero_fold_label':False}
        frames.append(f); samples.append({'file':f['file'],'sha256':f['crop_sha256'],'table_id':1,'actual_frame_timestamp_seconds':i})
    manifest={'source_sha256':ident['source_sha256'],'samples':samples}
    drafts={**ident,'status':'unverified_hand_timeline_drafts','hands_reconstructed':False,'actions_verified':False,
            'equity_ev_authorized':False,'automatic_clip_selection_authorized':False,'unassigned':[],
            'drafts':[{'draft_id':'d1','table_id':1,'hand_id':None,'complete_hand_verified':False,'frames':frames}]}
    review={'variant':5,'job_id':ident['job_id'],'draft_sha256':'d'*64,'draft_id':'d1','context_file':'f0.jpg','action_file':'f1.jpg',
            'reviewer':'synthetic fixture','context':context,'chosen_action':{'action':'call','extra_chips':0},
            'hypotheses':{} if preflop else {'base':s}}
    return binding,manifest,drafts,review,'d'*64


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.edb=sqlite3.connect(':memory:');self.addCleanup(self.edb.close)
        self.edb.execute('CREATE TABLE metadata(key,value)')
        self.edb.executemany('INSERT INTO metadata VALUES (?,?)',{'variant':'5','kind':'equity_vs_one_random_opponent',
            'csv_sha256':d.SHA256,'source':d.SOURCE,'license':d.LICENSE,'schema_version':'1'}.items())
        self.edb.execute('CREATE TABLE equity(rank,hand,suits,lo,hi,combos)')
        self.edb.execute("INSERT INTO equity VALUES (1,'A-A-A-A-K','ss','0.4','0.5',4)")
        self.sdb=d.store.connect(':memory:');self.addCleanup(self.sdb.close)

    def run_fixture(self,args):
        return d.analyze_review(*args,self.edb,self.sdb)

    def test_conditional_model_and_no_gto(self):
        r=self.run_fixture(fixture())
        self.assertEqual(r['status'],'CONDITIONAL_MODEL_ONLY')
        self.assertEqual(r['conditional_model']['conditional_loss_point_span_bb'],[0,0])
        self.assertEqual(r['starting_equity']['status'],'NOT_APPLICABLE_POSTFLOP')
        self.assertEqual(r['strategic_reference']['status'],'NO_MATCH')
        self.assertFalse(r['gto_solution']);self.assertIsNone(r['ev_loss_bb'])

    def test_preflop_descriptor_separate(self):
        r=self.run_fixture(fixture(True)); e=r['starting_equity']
        self.assertEqual((e['hand'],e['suits'],e['equity_lo']),('A-A-A-A-K','ss','0.4'))
        self.assertFalse(e['exact_suit_match']);self.assertIsNone(e['frequency']);self.assertIsNone(e['ev_bb'])
        self.assertIsNone(r['conditional_model']);self.assertEqual(r['status'],'NO_MATCH')

    def test_exact_reference_excludes_synthetic_and_wrong_node(self):
        args=fixture();c=args[3]['context'];src=d.store.add_source(self.sdb,'fixture','test','local')
        actions=[{'action':'fold','size':0,'frequency':1,'ev':0}]
        d.store.add_record(self.sdb,src,5,c,actions,synthetic=True)
        d.store.add_record(self.sdb,src,5,dict(c,node='other'),actions,synthetic=True)
        ref=self.run_fixture(args)['strategic_reference']
        self.assertEqual(ref['synthetic_matches_excluded'],1);self.assertIsNone(ref['frequency']);self.assertIsNone(ref['ev_bb'])
        self.assertEqual(ref['authorized_strategy_records'],0)

    def test_missing_or_conflicting_observations(self):
        for key,value in [('hero_cards',None),('board',None),('context',{}),('hero_fold_label',True)]:
            args=fixture();args[2]['drafts'][0]['frames'][0][key]=value
            r=self.run_fixture(args);self.assertEqual(r['status'],'INSUFFICIENT_DATA');self.assertIsNone(r['conditional_model'])
        args=fixture();args[2]['drafts'][0]['frames'][1]['actions'][0]['reading']['candidate']={'action':'fold'}
        self.assertEqual(self.run_fixture(args)['status'],'INSUFFICIENT_DATA')

    def test_provenance_order_and_coverage(self):
        for change in ('hash','job','variant','crop','same_frame','coverage'):
            args=fixture();r=args[3]
            if change=='hash':r['draft_sha256']='f'*64
            elif change=='job':r['job_id']='f'*32
            elif change=='variant':r['variant']=6
            elif change=='crop':args[2]['drafts'][0]['frames'][0]['crop_sha256']='f'*64
            elif change=='same_frame':r['action_file']=r['context_file']
            else:args[1]['samples'].append(dict(args[1]['samples'][0],file='missing.jpg'))
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_fixture(args)

    def test_model_context_and_precision(self):
        for key,val in [('pot',101),('hero_stack',301),('rake_bps',501),('opponent_street',31),('opponent_stack',301)]:
            args=fixture();args[3]['hypotheses']['base'][key]=val
            with self.assertRaises(ValueError):self.run_fixture(args)
        args=fixture();args[3]['context']['pot']='100.000000001'
        with self.assertRaisesRegex(ValueError,'precision'):self.run_fixture(args)

    def test_multiway_model_not_extrapolated(self):
        args=fixture();args[3]['context'].update(players=3,position='BTN')
        for f in args[2]['drafts'][0]['frames']:
            f['context']['hero_position_candidate']='BTN';f['actions'].append({'seat':3,'reading':{'candidate':None}})
        r=self.run_fixture(args);self.assertEqual(r['status'],'NO_MATCH');self.assertIn('multiway_model_not_supported',r['reasons'])
        self.assertIsNone(r['conditional_model'])

    def test_missing_opponent_and_persistent_action(self):
        args=fixture();args[2]['drafts'][0]['frames'][0]['context']['remaining_stacks_bb'].pop('2')
        self.assertEqual(self.run_fixture(args)['status'],'INSUFFICIENT_DATA')
        args=fixture();args[2]['drafts'][0]['frames'][0]['actions'][0]['reading']['candidate']={'action':'call'}
        self.assertEqual(self.run_fixture(args)['status'],'INSUFFICIENT_DATA')

    def test_unmodeled_sizing_not_substituted(self):
        args=fixture();args[3]['chosen_action']={'action':'raise','extra_chips':41}
        args[2]['drafts'][0]['frames'][1]['actions'][0]['reading']['candidate']={'action':'raise'}
        r=self.run_fixture(args);self.assertEqual(r['status'],'NO_MATCH')
        self.assertIsNone(r['conditional_model']['conditional_loss_point_span_bb'])

    def test_wrong_equity_metadata(self):
        self.edb.execute("UPDATE metadata SET value='6' WHERE key='variant'")
        with self.assertRaisesRegex(ValueError,'provenance'):self.run_fixture(fixture(True))

    @unittest.skipUnless(os.environ.get('PLO5_REVIEWED_EQUITY_DB') and all(shutil.which(x) for x in ('ffmpeg','ffprobe')), 'Requires reviewed snapshot and FFmpeg')
    def test_audited_mp4_and_full_snapshot(self):
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job, read_bound_evidence
        from offline_ingest_pts_audit import read_manifest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);video=root/'sample.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=green:s=128x128:r=5:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            regions=root/'regions.json';regions.write_text(json.dumps({'tables':[{'table_id':1,'x':0,'y':0,'width':128,'height':128}]}))
            jobs=root/'jobs.db';job=ingest_local(video,root/'uploads',jobs)
            res=run_job(jobs,job['job_id'],regions,root/'out',pixel_checks=1)
            binding=read_bound_evidence(jobs,job['job_id']);manifest=read_manifest(Path(res['result_path']).parent/'evidence/ingest/manifest.json')
            _,_,drafts,review,_=fixture(True)
            frames=drafts['drafts'][0]['frames'];frames.append(copy.deepcopy(frames[-1]))
            for f,s in zip(frames,manifest['samples']):f.update(file=s['file'],pts=s['actual_frame_timestamp_seconds'],crop_sha256=s['sha256'])
            drafts.update(job_id=job['job_id'],source_sha256=binding['source_sha256'],manifest_sha256=binding['reports']['evidence/ingest/manifest.json'])
            dp=root/'draft.json';dp.write_text(json.dumps(drafts))
            review.update(job_id=job['job_id'],draft_sha256=d.sha256(dp),context_file=frames[0]['file'],action_file=frames[1]['file'])
            rp=root/'review.json';rp.write_text(json.dumps(review))
            sp=root/'strategy.db';d.store.connect(sp).close()
            db=os.environ['PLO5_REVIEWED_EQUITY_DB'];out=root/'report.json'
            from contextlib import closing
            with closing(d.open_readonly(db,immutable=True)) as edb:
                self.assertEqual(edb.execute('SELECT count(*),sum(combos) FROM equity').fetchone(),(134459,2598960))
                self.assertEqual(dict(edb.execute('SELECT suits,sum(combos) FROM equity GROUP BY suits')),{
                    'ds':949104,'ss':685464,'3-suit':580008,'3+2':267696,'4-suit':111540,'mono':5148})
                desc=d.descriptor_reference(edb,{'street':'preflop','hero':['As','Ah','Ts','9h','9c']})
                self.assertGreater(desc['matches'],1);self.assertFalse(desc['exact_suit_match'])
            d.main([str(jobs),job['job_id'],str(dp),str(rp),db,str(sp),str(out)])
            r=json.loads(out.read_text());self.assertEqual(r['starting_equity']['rows'],[[110054,'0.44886','0.44906',4]])
            self.assertEqual(r['equity_database_sha256'],d.EQUITY_DB_SHA256)
            self.assertEqual(r['status'],'NO_MATCH');self.assertFalse(r['video_verified'])
            next((Path(res['result_path']).parent/'evidence/ingest').glob('*.jpg')).write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):d.analyze_job(jobs,job['job_id'],dp,rp,db,sp)


if __name__=='__main__':unittest.main()
