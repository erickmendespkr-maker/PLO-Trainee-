"""PLO5 cross-module regressions for missing evidence and mixed decisions."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import test_plo5_decision_analysis as bridge
import test_plo5_session_export as session
from plo5_leak_review import aggregate
from plo5_individual_report import build
from plo5_regression_runner import inventory, run_suite, snapshot, ROOT
from plo5_session_export import run, verify


def bundle(r):
    return {**{k:r[k] for k in ('variant','job_id','source_sha256','manifest_sha256','draft_sha256')},
            'draft_ids':[r['draft_id']], 'expected_decisions':[{'draft_id':r['draft_id'],'action_file':r['action_file']}],
            'reports':[r], 'financial_report':None}


class OfflineContracts(unittest.TestCase):
    def setUp(self):
        self.bridge=bridge.BridgeTests();self.bridge.setUp();self.addCleanup(self.bridge.doCleanups)

    def review(self,args):return self.bridge.run_fixture(args)

    def check_unverified(self,decision,classification,comparable):
        b=bundle(decision);summary=aggregate(b);individual=build(b)
        self.assertEqual(summary['decisions'][0]['classification'],classification)
        self.assertEqual(individual['classification'],classification)
        self.assertEqual(summary['overall']['fully_comparable_decisions'],comparable)
        for r in (decision,summary,individual):
            for k in ('gto_solution','video_verified','strategic_error_established','automatic_clip_selection_authorized'):self.assertIs(r[k],False)
            self.assertIsNone(r['ev_loss_bb'])
        self.assertIsNone(individual['frequency']);self.assertIsNone(individual['conditional_segment_net_bb'])
        return individual

    def test_mixed_synthetic_record_not_production_strategy(self):
        args=bridge.fixture();ctx=args[3]['context'];args[3]['hypotheses']={}
        db=self.bridge.sdb;store=bridge.d.store;source=store.add_source(db,'mixed fixture','test only','local')
        actions=[{'action':'fold','size':0,'frequency':.25,'ev':0},{'action':'call','size':20,'frequency':.5,'ev':51.25},{'action':'raise','size':60,'frequency':.25,'ev':51.25}]
        store.add_record(db,source,5,ctx,actions,synthetic=True)
        self.assertEqual(store.lookup(db,5,ctx),[]);self.assertTrue(store.lookup(db,5,ctx,synthetic=True))
        r=self.review(args);self.assertEqual(r['strategic_reference']['synthetic_matches_excluded'],1)
        out=self.check_unverified(r,'NO_MATCH',0);self.assertIn('Frequências GTO: indisponíveis',out['text']);self.assertEqual(out['scenarios'],[])

    def test_exact_tie_does_not_imply_mixing_frequency(self):
        r=self.review(bridge.fixture());out=self.check_unverified(r,'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES',1)
        s=r['conditional_model']['scenarios']['base'];self.assertEqual(s['point_best_actions'],[{'action':'call','extra_chips':0},{'action':'raise','extra_chips':40}]);self.assertEqual(s['conditional_ev_loss_bb'],0)
        self.assertIn('melhor ou empatada',out['text']);self.assertIn('Frequências GTO: indisponíveis',out['text'])

    def test_missing_exact_raise_sizing_remains_unscored(self):
        args=bridge.fixture();args[3]['chosen_action']={'action':'raise','extra_chips':41};args[2]['drafts'][0]['frames'][1]['actions'][0]['reading']['candidate']={'action':'raise'}
        r=self.review(args);out=self.check_unverified(r,'NO_MATCH',0)
        self.assertIn('Diferença indisponível',out['text']);self.assertIsNone(out['scenarios'][0]['conditional_ev_loss_bb'])

    def test_conflicting_board_stops_analysis(self):
        args=bridge.fixture();args[2]['drafts'][0]['frames'][0]['board']=None
        r=self.review(args);self.assertIn('cards_missing_or_conflicting',r['reasons'])
        out=self.check_unverified(r,'INSUFFICIENT_DATA',0);self.assertNotIn('Mão atual:',out['text']);self.assertEqual(out['scenarios'],[])

    def test_sensitivity_not_a_certified_leak(self):
        args=bridge.fixture();alt=copy.deepcopy(args[3]['hypotheses']['base']);alt['aggressions'][0]['call_bps']=[0,0,0];args[3]['hypotheses']['alt']=alt
        r=self.review(args);out=self.check_unverified(r,'SENSITIVE_OR_UNCERTAIN',1)
        self.assertIn('4,875 BB',out['text']);self.assertEqual(aggregate(bundle(r))['overall']['conditional_inferior_decisions'],0)

    def test_real_media_package_with_missing_and_insufficient_decisions(self):
        t=session.SessionTests;t.setUpClass();self.addCleanup(t.tearDownClass)
        req=copy.deepcopy(t.request);reports=[]
        for d in t.drafts['drafts']:
            fs=d['frames'];args=bridge.fixture();review=copy.deepcopy(args[3]);review.update(job_id=t.jid,draft_sha256=t.dh,draft_id=d['draft_id'],context_file=fs[0]['file'],action_file=fs[1]['file'],hypotheses={})
            if d['draft_id']=='d2':review['chosen_action']={'action':'fold','extra_chips':0}
            reports.append(bridge.d.analyze_review(t.binding,t.manifest,t.drafts,review,t.dh,self.bridge.edb,self.bridge.sdb))
        req['bundle']['reports']=reports;path=t.root/'contract_request.json';path.write_text(json.dumps(req));out=t.root/'contract_package'
        manifest=run(t.db,t.jid,t.dp,path,out);self.assertEqual(manifest,verify(out))
        result=json.loads((out/'session.json').read_text());self.assertEqual(result['overall']['classification_counts'],{'INSUFFICIENT_DATA':1,'MISSING_REPORT':2,'NO_MATCH':1});self.assertEqual(result['overall']['fully_comparable_decisions'],0)
        self.assertEqual(len(result['clips']),1);self.assertFalse(result['complete_hands_verified']);self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertEqual([r['clip'] for r in result['exported_decisions']],['hand_0001.mp4',None]);self.assertTrue(result['clips'][0]['decoded_yuv420p_pixels_match'])

    def test_runner_rejects_skips_and_duplicate_collection(self):
        class Dummy(unittest.TestCase):
            @unittest.skip('intentional sentinel')
            def test_skipped(self):pass
        r=run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Dummy),1,stream=io.StringIO());self.assertFalse(r['strict_pass']);self.assertEqual(r['skipped'],1)
        with self.assertRaisesRegex(ValueError,'duplicate'):run_suite(unittest.TestSuite([Dummy('test_skipped'),Dummy('test_skipped')]),2,stream=io.StringIO())
        with self.assertRaisesRegex(ValueError,'collection'):run_suite(unittest.TestSuite(),1,stream=io.StringIO())

    def test_runner_source_and_snapshot_integrity(self):
        r=inventory(candidate=True);self.assertEqual(r['baseline_files'],81)
        self.assertIn('offline_real_video_probe',r['source_blobs']);self.assertIn('offline_board_street_proposals',r['source_blobs'])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.sqlite';p.write_bytes(b'not reviewed')
            with self.assertRaisesRegex(ValueError,'Unreviewed'):snapshot(p)


if __name__=='__main__':unittest.main()
