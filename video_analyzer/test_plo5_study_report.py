import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_study_report import build,main
from plo5_strategy_integration import integrate
from test_plo5_strategy_integration import args_for,preflop_case,stackoff_case,multiway_case,river_case
import test_plo5_decision_analysis as fixtures
from test_plo5_leak_review import bundle,IDENT
from test_plo5_individual_report import reviewed


def example(s,kind,bridge):
    a,e=args_for(s,kind);r=integrate(*a,bridge.edb,bridge.sdb,e,trials=20,iterations=2000);b=r['base_decision'];f=b['action_file'];d=b['draft_id']
    return {'bundle':{**IDENT,'draft_ids':[d],'expected_decisions':[{'draft_id':d,'action_file':f}],'reports':[b],'financial_report':None},'integrations':[{'review':a[3],'extension':e,'report':r}]}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.t=fixtures.BridgeTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
    def test_roster_missing_and_recurrence(self):
        r=build({'bundle':bundle(),'integrations':[]});self.assertEqual((r['declared_decisions'],r['reports_received'],r['comparable_decisions']),(7,6,4));self.assertEqual(r['classification_counts']['MISSING_REPORT'],1);self.assertTrue(any(x['repeated_conditional_pattern'] for x in r['patterns']));self.assertIsNone(r['ev_loss_bb'])
    def test_all_families_and_modes(self):
        for kind,s in [('preflop',preflop_case()),('stackoff',stackoff_case()),('multiway',multiway_case()),('river',river_case())]:
            p=example(s,kind,self.t);q=build(p);d=build(p,'deep');r=q['decisions'][0];self.assertEqual(r['model_family'],kind);self.assertEqual(q['classification_counts'],d['classification_counts']);self.assertFalse(q['gto_solution']);self.assertEqual(q['solver_reruns'],0)
            if kind=='multiway':self.assertIn('9,300 BB',r['text']);self.assertEqual(r['loss_bounds_bb'],[0,0]);self.assertIn('cartas de conclusão',d['decisions'][0]['text'])
            if kind=='river':self.assertEqual(r['classification'],'RESTRICTED_GAME_ONLY');self.assertIsNone(r['loss_bounds_bb']);self.assertIn('frequência do jogo restrito',r['text'])
            if kind=='preflop':self.assertIn('rfi',r['text']);self.assertIsNone(r['loss_bounds_bb'])
            if kind=='stackoff':self.assertIn('Stack-off HU',r['text']);self.assertIn('EV terminal',r['text'])
    def test_identity_and_numeric_tamper(self):
        p=example(multiway_case(),'multiway',self.t)
        for key in ('identity','ev','share','interval','implied','duplicate','flags'):
            x=copy.deepcopy(p);i=x['integrations'][0];r=i['report'];m=r['extension_result']
            if key=='identity':i['review']['reviewer']='other'
            elif key=='ev':m['scenarios']['base']['ev_call_bb']=90
            elif key=='share':m['equity_model']['share_mass'][0]+=1
            elif key=='interval':m['scenarios']['base']['sampling_ci95_bb']=[-100,100]
            elif key=='implied':m['scenarios']['future']['expected_implied_gain_bb']=999
            elif key=='duplicate':x['integrations'].append(i)
            else:r['gto_solution']=True
            with self.subTest(key=key),self.assertRaises(ValueError):build(x)
    def test_quick_avoids_draws_deep_cache(self):
        p=example(multiway_case(),'multiway',self.t);b=p['bundle'];r=copy.deepcopy(b['reports'][0]);r['action_file']='second.jpg';r['context_file']='prior.jpg';b['reports'].append(r);b['expected_decisions'].append({'draft_id':r['draft_id'],'action_file':'second.jpg'})
        with patch('plo5_study_report.draws',side_effect=AssertionError('no draws in quick')):q=build(p)
        self.assertEqual(q['card_cache']['hits'],1);d=build(p,'deep');self.assertEqual(d['card_cache']['hits'],1);self.assertEqual(d['card_cache']['misses'],1)
    def test_insufficient_no_details(self):
        r=reviewed();r.update(status='INSUFFICIENT_DATA',conditional_model=None);b={**IDENT,'draft_ids':[r['draft_id']],'expected_decisions':[{'draft_id':r['draft_id'],'action_file':r['action_file']}],'reports':[r],'financial_report':None};q=build({'bundle':b,'integrations':[]});self.assertNotIn('Mão atual',q['decisions'][0]['text']);self.assertEqual(q['card_cache']['misses'],0)
    def test_cli(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'in.json';o=Path(t)/'out.json';p.write_text(json.dumps({'bundle':bundle(),'integrations':[]}));main([str(p),str(o)]);self.assertEqual(len(json.loads(o.read_text())['input_sha256']),64)
            with self.assertRaises(ValueError):main([str(p),str(o)])

if __name__=='__main__':unittest.main()
