import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_selective_review import select,evaluate_models,model_state,STREETS
from test_plo5_post_gto_river import polar,CATCH


def row(street='flop',ident='a',actual='call:2',lo=0,hi=0,alt=(.01,.01)):
    return dict(hand_id='h',decision_id=ident,street=street,action=actual,
                action_ev_bounds={actual:[lo,hi],'fold:0':list(alt)},
                reconstruction_verified=True,strategy_verified=True,action_set_complete=True,
                ev_basis='incremental_bb',certificate_sha256='a'*64,pot_odds=1/3,
                evidence=dict(source_sha256='b'*64,rgb_sha256='c'*64,pts='100/3',table_id=1,phase='before',hand_id='h',decision_id=ident,street=street))


class SelectiveReviewTests(unittest.TestCase):
    def test_independent_streets_and_marginal(self):
        a=row();b=row('turn','b',lo=2,hi=2);c=row('river','c',alt=(7,7));r=select([a,b,c])
        self.assertEqual([e['decision_id'] for e in r['errors']],['c','a']);self.assertEqual([e['severity'] for e in r['errors']],['grave','marginal']);self.assertEqual(r['adequate_count'],1)
        self.assertEqual({e['decision_id'] for e in r['print_requests']},{'a','c'})
        self.assertFalse(r['prints_extracted'])
    def test_street_filter_and_result_independence(self):
        a=row();b=row('turn','b');c=row('river','c');r=select([a,b,c],['river','flop'])
        self.assertEqual(r['streets'],['flop','river']);self.assertEqual(r['evaluated'],2);self.assertEqual(r['by_street']['turn']['excluded'],1)
        self.assertEqual(select([a]),select([dict(a,net_bb=200)]));self.assertEqual(select([a]),select([dict(a,net_bb=-200)]))
    def test_uncertainty_and_missing_evidence(self):
        a=row();a['strategy_verified']=False;b=row('flop','b',hi=1,alt=(0,2));c=row('turn','c');c['evidence']=None
        r=select([a,b,c]);self.assertEqual(len(r['unresolved']),2);self.assertEqual(r['errors'][0]['evidence_status'],'MISSING_REFERENCE');self.assertFalse(r['print_requests'])
        self.assertFalse(select([dict(row(),action_set_complete=False)])['errors'])
    def test_reject_duplicates_invalid_bounds_and_references(self):
        a=row()
        with self.assertRaises(ValueError):select([a,a],['river'])
        with self.assertRaises(ValueError):select([a],['flop','flop'])
        with self.assertRaises(ValueError):select([dict(a,action_ev_bounds={'call:2':[0,float('nan')]})])
        with self.assertRaises(ValueError):select([dict(a,evidence=dict(a['evidence'],decision_id='other'))])
        with self.assertRaises(ValueError):select([dict(a,evidence=dict(a['evidence'],pts='1.0'))])
    def test_distinct_raise_sizes(self):
        a=row(actual='raise:10');a['action_ev_bounds']={'raise:10':[0,0],'raise:20':[.001,.001]}
        r=select([a]);self.assertEqual(r['errors'][0]['recommended'],'raise:20')
    def test_native_adapter_and_spr(self):
        m=dict(context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=10)
        d=dict(hand_id='h',decision_id='a',street='river',model=m)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'cache.sqlite';r=evaluate_models(p,[d],['river'],cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
            self.assertFalse(r['errors']);self.assertFalse(r['print_requests']);self.assertEqual(len(r['unresolved']),1)
            e=r['experimental_estimates'][0];self.assertFalse(e['certified']);self.assertAlmostEqual(e['model']['pot_odds_gross'],1/3);self.assertEqual(e['state']['effective_spr_street_start'],1)
            with patch('plo5_review.postflop') as f:
                r=evaluate_models(p,[d],['flop']);f.assert_not_called();self.assertEqual(r['evaluated'],0)
                with self.assertRaisesRegex(ValueError,'Street does not match'):evaluate_models(p,[dict(d,street='turn')],['flop'])
                f.assert_not_called()
    def test_preflop_filter(self):
        a=row('preflop');self.assertEqual(len(select([a],['preflop'])['errors']),1)

if __name__=='__main__':unittest.main()
