import copy
import json
from pathlib import Path
import tempfile
import unittest

from plo5_leak_review import aggregate, main, bucket
from plo5_ev_comparison import compare
from test_plo5_action_ev import scenario
from test_plo5_decision_analysis import fixture
import test_plo5_decision_analysis as bridge
from strategic_normalize import normalize_scenario
from test_plo5_financial_reconcile import fixture as ledger_fixture, review
from plo5_financial_reconcile import build

IDENT={'variant':5,'job_id':'a'*32,'source_sha256':'b'*64,'manifest_sha256':'c'*64,'draft_sha256':'d'*64}


def report(i, draft, action='fold', model=True, mixed=False, mc=False):
    s=scenario();chosen={'action':action,'extra_chips':41 if action=='raise' else 0}
    hypotheses={'base':s}
    if mixed:
        alt=copy.deepcopy(s);alt['aggressions'][0]['call_bps']=[0,0,0];hypotheses['fold_all']=alt
    m=compare(hypotheses,chosen,**({'method':'monte_carlo','trials':20,'seed':1} if mc else {})) if model else None
    status='CONDITIONAL_MODEL_ONLY' if m and m['coverage']['hypotheses_comparable'] else 'NO_MATCH'
    return {**IDENT,'draft_id':draft,'context_file':f'c{i}.jpg','action_file':f'a{i}.jpg','context_pts':i*2,'action_pts':i*2+1,
            'context':normalize_scenario(5,fixture()[3]['context']),'chosen_action_declared':chosen,'status':status,'conditional_model':m,
            'video_verified':False,'gto_solution':False,'strategic_error_established':False,'automatic_clip_selection_authorized':False,'financial_result_bb':None,'ev_loss_bb':None}


def bundle():
    reports=[report(1,'d1'),report(2,'d2'),report(3,'d1','call'),report(4,'d3','call',mixed=True),report(5,'d4','call',model=False),report(6,'d4','raise')]
    return {**IDENT,'draft_ids':['d1','d2','d3','d4','d5'],'expected_decisions':[{'draft_id':r['draft_id'],'action_file':r['action_file']} for r in reports]+[{'draft_id':'d5','action_file':'a7.jpg'}],'reports':reports,'financial_report':None}


class LeakTests(unittest.TestCase):
    def test_coverage_and_recurrence(self):
        r=aggregate(bundle());o=r['overall']
        self.assertEqual((o['declared_decisions'],o['reports_received'],o['fully_comparable_decisions']),(7,6,4))
        self.assertAlmostEqual(o['coverage_fraction'],4/7)
        self.assertEqual(o['classification_counts'],{'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES':1,'INFERIOR_IN_ALL_DECLARED_HYPOTHESES':2,'MISSING_REPORT':1,'NO_MATCH':2,'SENSITIVE_OR_UNCERTAIN':1})
        self.assertEqual(o['conditional_inferior_fraction_of_comparable'],.5);self.assertAlmostEqual(o['conditional_inferior_fraction_of_declared'],2/7)
        self.assertTrue(o['repeated_conditional_pattern']);self.assertEqual(o['distinct_inferior_draft_segments'],2)
        self.assertIsNone(o['conditional_loss_total_bb']);self.assertIsNone(o['verified_leak_count']);self.assertFalse(r['full_session_coverage_verified'])

    def test_same_draft_not_recurrence(self):
        b=bundle();b['reports'][1]['draft_id']='d1';b['expected_decisions'][1]['draft_id']='d1'
        o=aggregate(b)['overall'];self.assertEqual(o['conditional_inferior_decisions'],2);self.assertFalse(o['repeated_conditional_pattern'])

    def test_groups_and_unknown_context(self):
        r=aggregate(bundle());g=r['groups']
        for groups in g.values():self.assertEqual(sum(x['declared_decisions'] for x in groups),7)
        fold=next(x for x in g['combined'] if x['action']=='fold')
        self.assertEqual((fold['position'],fold['street'],fold['players_dealt'],fold['hero_remaining_stack_bucket_bb']),('SB','river',2,'20_to_under_50'))
        self.assertEqual(fold['coverage_fraction'],1);self.assertTrue(fold['repeated_conditional_pattern'])
        unknown=next(x for x in g['position'] if x['position'] is None);self.assertEqual(unknown['declared_decisions'],1);self.assertEqual(unknown['coverage_fraction'],0)
        self.assertEqual([bucket(str(x)) for x in (0,19,20,49,50,99,100,199,200)],['0_to_under_20']*2+['20_to_under_50']*2+['50_to_under_100']*2+['100_to_under_200']*2+['200_plus'])

    def test_monte_carlo_and_sensitivity(self):
        b=bundle();b['reports'][2]=report(3,'d1','call',mc=True)
        r=aggregate(b);self.assertEqual(r['decisions'][2]['classification'],'SENSITIVE_OR_UNCERTAIN')
        self.assertAlmostEqual(r['overall']['sampling_joint_coverage_lower_bound'],.9)
        self.assertEqual(r['decisions'][3]['loss_bounds_bb'],[0,4.875])

    def test_financial_separation_and_coverage(self):
        b=bundle();r=build(*ledger_fixture(review([('contribution','45')],'55')))
        r['unreviewed_draft_ids']=['d2','d3','d4','d5'];b['financial_report']=r
        out=aggregate(b);f=out['financial'];self.assertEqual(f['conditional_net_bb'],-45);self.assertEqual(f['reconciled_drafts'],1);self.assertEqual(f['unreviewed_drafts'],4)
        self.assertFalse(f['net_covers_all_declared_drafts']);self.assertIsNone(out['ev_loss_bb']);self.assertIsNone(out['variance_attribution']);self.assertEqual(out['overall']['conditional_inferior_decisions'],2)
        r['reviews'][0]['conditional_net_bb']='-44'
        with self.assertRaises(ValueError):aggregate(b)

    def test_mixed_provenance_duplicates_and_verified_claims(self):
        for change in ('job','source','manifest','draft','variant','duplicate_roster','duplicate_report','unknown_draft','verified','gto','ev','noncanonical'):
            b=bundle();r=b['reports'][0]
            if change=='job':r['job_id']='f'*32
            elif change in ('source','manifest','draft'):r[change+'_sha256']='f'*64
            elif change=='variant':r['variant']=6
            elif change=='duplicate_roster':b['expected_decisions'].append(b['expected_decisions'][0])
            elif change=='duplicate_report':b['reports'].append(r)
            elif change=='unknown_draft':r['draft_id']='other'
            elif change=='verified':r['video_verified']=True
            elif change=='gto':r['gto_solution']=True
            elif change=='ev':r['ev_loss_bb']=5
            else:r['context']['stack']='30.000'
            with self.subTest(change=change),self.assertRaises(ValueError):aggregate(b)

    def test_reject_tampered_model(self):
        for change in ('loss','bounds','classification','coverage','action','interval','span'):
            b=bundle();m=b['reports'][0]['conditional_model'];s=m['scenarios']['base']
            if change=='loss':s['conditional_ev_loss_fraction_bb']['numerator']=99
            elif change=='bounds':s['loss_bounds_bb']=[1,8]
            elif change=='classification':s['status']='BEST_OR_TIED_UNDER_BOUNDS'
            elif change=='coverage':m['coverage']['hypotheses_comparable']=0
            elif change=='action':m['chosen_action_declared']={'action':'call','extra_chips':0}
            elif change=='interval':m['sampling_interval_joint_coverage_lower_bound']=.5
            else:m['conditional_loss_bounds_span_bb']=[0,8]
            with self.subTest(change=change),self.assertRaises(ValueError):aggregate(b)

    def test_missing_and_empty_denominators(self):
        b=bundle();b['reports']=[];r=aggregate(b);self.assertEqual(r['overall']['coverage_fraction'],0);self.assertIsNone(r['overall']['conditional_inferior_fraction_of_comparable'])
        b['expected_decisions']=[];r=aggregate(b);self.assertIsNone(r['overall']['coverage_fraction']);self.assertFalse(r['overall']['repeated_conditional_pattern'])

    def test_actual_review_bridge_report(self):
        t=bridge.BridgeTests();t.setUp()
        try:r=t.run_fixture(fixture())
        finally:t.doCleanups()
        b={**IDENT,'draft_ids':['d1'],'expected_decisions':[{'draft_id':'d1','action_file':'f1.jpg'}],'reports':[r],'financial_report':None}
        o=aggregate(b)['overall'];self.assertEqual(o['fully_comparable_decisions'],1);self.assertEqual(o['conditional_inferior_decisions'],0)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bundle.json';q=Path(tmp)/'report.json';p.write_text(json.dumps(bundle()))
            self.assertEqual(main([str(p),str(q)]),0);r=json.loads(q.read_text());self.assertEqual(r['overall']['declared_decisions'],7);self.assertEqual(len(r['input_sha256']),64)
            with self.assertRaises(ValueError):main([str(p),str(q)])
            p.write_text('{"variant":5,"variant":6}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):main([str(p),str(Path(tmp)/'other.json')])


if __name__=='__main__':unittest.main()
