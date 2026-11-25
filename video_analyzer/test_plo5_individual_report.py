import copy
import json
import tempfile
import unittest
from pathlib import Path

import test_plo5_decision_analysis as bridge
from test_plo5_leak_review import bundle, report
from test_plo5_financial_reconcile import fixture as ledger_fixture, review
from plo5_financial_reconcile import build as build_ledger
from plo5_individual_report import build, main


def one(r):
    b=bundle();b['reports']=[r];b['expected_decisions']=[{'draft_id':r['draft_id'],'action_file':r['action_file']}]
    return b


def reviewed(preflop=False):
    t=bridge.BridgeTests();t.setUp()
    try:return t.run_fixture(bridge.fixture(preflop))
    finally:t.doCleanups()


class IndividualTests(unittest.TestCase):
    def test_exact_tie_and_equity(self):
        r=build(one(reviewed()));text=r['text']
        self.assertEqual(r['classification'],'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES')
        self.assertIn('5,125 BB',text);self.assertIn('62,50%',text);self.assertIn('50,00%',text)
        self.assertIn('Mão atual:',text);self.assertIn('16,67%',text)
        self.assertIsNone(r['frequency']);self.assertIsNone(r['ev_loss_bb']);self.assertFalse(r['gto_solution'])

    def test_inferior_fold_and_sensitivity(self):
        r=build(one(report(1,'d1')));self.assertIn('EV inferior em todas',r['text']);self.assertIn('5,125 BB',r['text'])
        r=build(one(report(1,'d1','call',mixed=True)));self.assertEqual(r['classification'],'SENSITIVE_OR_UNCERTAIN');self.assertIn('4,875 BB',r['text'])

    def test_preflop_descriptor_and_no_match(self):
        r=build(one(reviewed(True)));self.assertIn('40,00% a 50,00%',r['text']);self.assertIn('não há correspondência exata de naipes',r['text']);self.assertIn('Sem modelo compatível',r['text'])
        self.assertEqual(r['classification'],'NO_MATCH')

    def test_no_sizing_match_and_old_report(self):
        r=build(one(report(1,'d1','raise')));self.assertIn('41 fichas acima do call',r['text']);self.assertIn('Diferença indisponível',r['text'])
        old=report(1,'d1','call')
        for a in old['conditional_model']['scenarios']['base']['alternatives']:a.pop('showdown_equity')
        self.assertNotIn('Equity de showdown',build(one(old))['text'])

    def test_mc_uncertainty(self):
        r=build(one(report(1,'d1','call',mc=True)));self.assertIn('90,00%',r['text']);self.assertIn('20 estados/amostras',r['text']);self.assertEqual(r['classification'],'SENSITIVE_OR_UNCERTAIN')

    def test_financial_separate(self):
        b=one(report(1,'d1'));f=build_ledger(*ledger_fixture(review([('contribution','45')],'55')));f['unreviewed_draft_ids']=['d2','d3','d4','d5'];b['financial_report']=f
        r=build(b);self.assertEqual(r['conditional_segment_net_bb'],'-45');self.assertIn('-45 BB (ledger declarado',r['text']);self.assertIsNone(r['variance_attribution'])

    def test_inconsistent_context_not_described(self):
        r=reviewed();r.update(status='INSUFFICIENT_DATA',conditional_model=None)
        out=build(one(r));self.assertNotIn('Mão atual:',out['text']);self.assertIn('Contexto insuficiente',out['text'])

    def test_tamper_and_variant(self):
        for change in ('variant','model','equity','ref'):
            r=reviewed(change=='ref')
            if change=='variant':r['variant']=6
            elif change=='model':r['conditional_model']['scenarios']['base']['conditional_ev_loss_bb']=99
            elif change=='equity':next(a for a in r['conditional_model']['scenarios']['base']['alternatives'] if a['showdown_equity'])['showdown_equity']['equity_fraction']['numerator']=99
            else:r['starting_equity']['equity_lo']='0.1'
            with self.subTest(change=change),self.assertRaises(ValueError):build(one(r))
        with self.assertRaises(ValueError):build(bundle())

    def test_cli_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bundle.json';q=Path(tmp)/'out.json';t=Path(tmp)/'out.txt';p.write_text(json.dumps(one(reviewed())))
            self.assertEqual(main([str(p),str(q)]),0);self.assertEqual(main([str(p),str(t)]),0)
            r=json.loads(q.read_text());self.assertEqual(len(r['input_sha256']),64);self.assertIn(r['input_sha256'],t.read_text());self.assertIn('Rastreabilidade',r['text'])
            with self.assertRaises(ValueError):main([str(p),str(q)])


if __name__=='__main__':unittest.main()
