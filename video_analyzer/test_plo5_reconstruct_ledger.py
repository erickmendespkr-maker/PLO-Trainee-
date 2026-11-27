import unittest
from fractions import Fraction
from plo5_reconstruct_ledger import replay,reconcile

H={'SB':['As','Ks','Qh','Jd','Tc'],'BB':['Ah','Kh','Qs','Jc','Td']}
B=['2c','3d','4h','5s','6s']
def action(p,a,v=0):return dict(position=p,action=a,amount=v)
def run(stacks,events,h=None,**kw):return replay(stacks,1,2,events,h or {},**dict(dict(rake_bps=0,rake_cap=0,rake_on_fold=False),**kw))

class LedgerReplayTests(unittest.TestCase):
    def test_fold_and_rebuy(self):
        r=run({'SB':200,'BB':200},[action('SB','fold')]);self.assertEqual(r['net_chips'],{'SB':-1,'BB':1});self.assertEqual(r['returned']['BB'],1)
        a=reconcile(r,{'SB':0,'BB':2},{'SB':0,'BB':1},0,{'SB':199,'BB':201},{'SB':1,'BB':0},{'SB':200,'BB':201})
        self.assertEqual(a['status'],'DECLARED_SETTLEMENT_MATCH');self.assertEqual(a['net_chips']['SB'],-1);self.assertFalse(a['financial_result_verified'])
        a=reconcile(r,{'SB':0,'BB':2},{'SB':0,'BB':1},0,{'SB':200,'BB':200},{'SB':0,'BB':0},{'SB':200,'BB':200});self.assertEqual(a['status'],'SETTLEMENT_MISMATCH');self.assertIsNone(a['net_chips'])
    def test_allin_and_tie(self):
        r=run({'SB':4,'BB':4},[action('SB','raise',3),action('BB','call',2),{'cards':B[:3]},{'cards':B[3:4]},{'cards':B[4:]}],H)
        self.assertEqual(sum(r['net_chips'].values()),0);self.assertEqual(r['board'],B);self.assertEqual(r['contributions'],{'SB':4,'BB':4})
    def test_full_streets(self):
        events=[action('SB','call',1),action('BB','check'),{'cards':B[:3]},action('BB','bet',4),action('SB','call',4),{'cards':B[3:4]},action('BB','check'),action('SB','check'),{'cards':B[4:]},action('BB','check'),action('SB','check')]
        r=run({'SB':200,'BB':200},events,H,rake_bps=1000,rake_cap=10)
        self.assertEqual(r['contributions'],{'BB':6,'SB':6});self.assertEqual(r['rake'],1);self.assertEqual(sum(r['net_chips'].values()),-1)
    def test_threeway_side_pot(self):
        h=dict(H,BTN=['7c','8d','9h','Ts','Js'])
        events=[action('BTN','raise',7),action('SB','raise',11),action('BB','call',10),action('BTN','call',5),{'cards':B[:3]},action('BB','bet',8),action('BTN','call',8),{'cards':B[3:4]},{'cards':B[4:]}]
        # SB has 12 chips, other two have 20; original 12-chip contribution remains eligible.
        r=run({'BTN':20,'SB':12,'BB':20},events,h)
        self.assertEqual(r['contributions'],{'SB':12,'BB':20,'BTN':20});self.assertEqual([x['gross'] for x in r['layers']],[36,16]);self.assertEqual(sum(r['net_chips'].values()),0)
    def test_incomplete_illegal_and_blockers(self):
        for events in ([action('BB','check')],[action('SB','call',1)],[{'cards':B[:3]}],[action('SB','raise',199)]):
            with self.assertRaises(ValueError):run({'SB':200,'BB':200},events)
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_SHOWDOWN'):run({'SB':4,'BB':4},[action('SB','raise',3),action('BB','call',2)])
        with self.assertRaises(ValueError):run({'SB':200,'BB':200},[],dict(H,BB=H['SB']))

if __name__=='__main__':unittest.main()
