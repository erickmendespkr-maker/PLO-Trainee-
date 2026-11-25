import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_plo5_decision_analysis as fixtures
from test_plo5_preflop_context import scenario as preflop_case
from test_plo5_stackoff import scenario as stackoff_case
from test_plo5_multiway_implied import scenario as multiway_case
from test_plo5_river_solver import fixture as river_case
from plo5_strategy_integration import integrate,digest,run
from plo5_preflop_context import analyze as preflop
from plo5_stackoff import analyze as stackoff


def args_for(s,kind):
    args=fixtures.fixture(kind in ('preflop','stackoff'));r=args[3];r['hypotheses']={};c=r['context'];board=s.get('board',[])
    if kind in ('preflop','stackoff'):
        report=(preflop if kind=='preflop' else stackoff)(s,trials=10);pos=s['position'];h=s['hero'];stacks=report['remaining_stacks_chips'];order=list(stacks);order.remove(pos);order.insert(0,pos);mapping={p:i+1 for i,p in enumerate(order)};values={str(i):str(stacks[p]/s['bb']) for p,i in mapping.items()};pot=report['pot_chips'];call=report['to_call_chips'];stack=stacks[pos];bb=s['bb'];rate=s['rake_bps'];cap=s['rake_cap'];chosen={'action':s['chosen']['action'],'extra_chips':s['chosen']['amount']-call if s['chosen']['action']=='raise' else 0}
    elif kind=='multiway':
        pos='BTN';h=s['hero'];bb=s['bb_chips'];stack=s['hero_stack_chips'];pot=s['pot_chips'];call=s['call_chips'];rate=s['rake_bps'];cap=s['rake_cap_chips'];values={'1':str(stack/bb),**{str(i+2):str(v/bb) for i,v in enumerate(s['opponent_stacks_chips'])}};mapping={str(i):i+2 for i in range(len(s['ranges']))};chosen={'action':'call','extra_chips':0}
    else:
        pos='SB';h=s['hero_range'][0]['cards'];bb=s['bb_chips'];stack=s['hero_stack_chips'];pot=s['pot_chips'];call=rate=cap=0;values={'1':str(stack/bb),'2':str(s['opponent_stack_chips']/bb)};mapping={'opponent':2};chosen={'action':'bet','extra_chips':s['bet_chips']}
    c.update(players=len(values),position=pos,street={0:'preflop',3:'flop',4:'turn',5:'river'}[len(board)],hero=h,board=board,bb_size=bb,stack=stack,pot=pot,to_call=call,rake_percent=rate/100,rake_cap=cap);r['chosen_action']=chosen
    for i,f in enumerate(args[2]['drafts'][0]['frames']):
        f.update(hero_cards=h,board=board,context={'hero_position_candidate':pos,'pot_bb':str(pot/bb),'remaining_stacks_bb':values},actions=[{'seat':int(k),'reading':{'candidate':{'action':chosen['action']} if i and k=='1' else None}} for k in values])
    return args,{'variant':5,'review_digest':digest(r),'kind':kind,'scenario':s,'seat_map':mapping}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.bridge=fixtures.BridgeTests();self.bridge.setUp();self.addCleanup(self.bridge.doCleanups)
    def run_case(self,a,e):return integrate(*a,self.bridge.edb,self.bridge.sdb,e,trials=20,iterations=2000)
    def test_preflop_sixmax(self):
        a,e=args_for(preflop_case(),'preflop');r=self.run_case(a,e);self.assertEqual(r['extension_result']['chosen_class'],'rfi');self.assertEqual(r['model_status'],'NO_MATCH');self.assertIsNone(r['frequency'])
    def test_stackoff(self):
        a,e=args_for(stackoff_case(),'stackoff');r=self.run_case(a,e);self.assertEqual(r['extension_result']['chosen_raise_number'],4);self.assertTrue(r['extension_result']['chosen_all_in']);self.assertIsNone(r['ev_loss_bb'])
    def test_multiway(self):
        a,e=args_for(multiway_case(),'multiway');r=self.run_case(a,e);self.assertEqual(r['model_status'],'CONDITIONAL_MODEL_ONLY');self.assertEqual(r['chosen_conditional_model']['base']['ev_bb'],9.3);self.assertFalse(r['gto_solution']);self.assertEqual(r['extension_result']['equity_model']['players'],3)
    def test_river(self):
        a,e=args_for(river_case(),'river');r=self.run_case(a,e);self.assertEqual(r['model_status'],'RESTRICTED_RIVER_GAME_APPROXIMATION');self.assertEqual(len(r['chosen_conditional_model']['actions']),2);self.assertIsNone(r['frequency']);self.assertFalse(r['video_verified'])
    def test_missing_evidence_blocks_extension(self):
        a,e=args_for(multiway_case(),'multiway');a[2]['drafts'][0]['frames'][0]['board']=None
        with patch('plo5_strategy_integration.multiway',side_effect=AssertionError('must not run')):r=self.run_case(a,e)
        self.assertEqual(r['model_status'],'INSUFFICIENT_DATA');self.assertIsNone(r['extension_result'])
    def test_mismatches(self):
        for k,v in [('pot_chips',101),('bb_chips',11),('opponent_stacks_chips',[149,120]),('rake_bps',501)]:
            a,e=args_for(multiway_case(),'multiway');e['scenario'][k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):self.run_case(a,e)
        a,e=args_for(preflop_case(),'preflop');e['seat_map']['UTG']=2
        with self.assertRaises(ValueError):self.run_case(a,e)
        a,e=args_for(river_case(),'river');e['scenario']['bet_chips']=99
        with self.assertRaises(ValueError):self.run_case(a,e)
    def test_review_digest_and_no_model_mixing(self):
        a,e=args_for(preflop_case(),'preflop');a[3]['reviewer']='different'
        with self.assertRaises(ValueError):self.run_case(a,e)
        a,e=args_for(preflop_case(),'preflop');a[3]['hypotheses']={'duplicate':{}};e['review_digest']=digest(a[3])
        with self.assertRaises(ValueError):self.run_case(a,e)
    def test_none_preserves_existing_bridge(self):
        a=fixtures.fixture();r=self.run_case(a,{'variant':5,'review_digest':digest(a[3]),'kind':'none','scenario':None,'seat_map':{}});self.assertEqual(r['base_decision']['status'],'CONDITIONAL_MODEL_ONLY');self.assertIsNone(r['extension_result'])

    @unittest.skipUnless(os.environ.get('PLO5_REVIEWED_EQUITY_DB'),'Requires reviewed snapshot')
    def test_bound_mp4_job_and_tamper(self):
        from test_plo5_session_export import SessionTests
        t=SessionTests;t.setUpClass();self.addCleanup(t.tearDownClass)
        _,_,_,r,_=fixtures.fixture();fs=t.drafts['drafts'][0]['frames'];r.update(job_id=t.jid,draft_sha256=t.dh,draft_id='d1',context_file=fs[0]['file'],action_file=fs[1]['file'])
        rp=t.root/'review44.json';ep=t.root/'extension44.json';sp=t.root/'strategy44.db';fixtures.d.store.connect(sp).close();rp.write_text(json.dumps(r));ep.write_text(json.dumps({'variant':5,'review_digest':digest(r),'kind':'none','scenario':None,'seat_map':{}}));db=os.environ['PLO5_REVIEWED_EQUITY_DB']
        result=run(t.db,t.jid,t.dp,rp,db,sp,ep);self.assertEqual(result['base_decision']['status'],'CONDITIONAL_MODEL_ONLY');self.assertFalse(result['video_verified']);self.assertEqual(result['equity_database_sha256'],fixtures.d.EQUITY_DB_SHA256)
        next((Path(fixtures.d.OfflineJobStore(t.db).get(t.jid)['result_path']).parent/'evidence/ingest').glob('*.jpg')).write_bytes(b'tampered')
        with self.assertRaises(ValueError):run(t.db,t.jid,t.dp,rp,db,sp,ep)

if __name__=='__main__':unittest.main()
