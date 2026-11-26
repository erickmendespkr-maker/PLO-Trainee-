import copy
import unittest
from plo5_balance_review import triage,reconcile,digest
from plo5_window_review import build
from test_plo5_window_review import window


def fixture(values=('100','20','100','100')):
    w=window(1,0,[[],[],[],[]]);t=w['timeline'];w['money']=dict(variant=5,job_id=t['job_id'],source_sha256=t['source_sha256'],financial_result_verified=False,observations=[dict(file=r['file'],table_id=r['table_id'],pts=r['pts'],crop_sha256=r['sha256'],stack_bb=v,pot_bb=None) for r,v in zip(t['observations'],values)])
    return build([w])


def declaration(r,transfers=(),complete=True):
    s=r['segments'][0];f=s['frames'];return {'variant':5,'review_sha256':digest(r),'reviews':[{'candidate_id':s['candidate_id'],'reviewer':'test','same_hand_and_settled':complete,'transfers_complete':complete,'before':{'file':f[0]['file'],'bb':f[0]['stack_bb']},'after':{'file':f[-1]['file'],'bb':f[-1]['stack_bb']},'transfers':list(transfers)}]}

class BalanceTests(unittest.TestCase):
    def test_drawdown_not_loss(self):
        r=triage(fixture())['rows'][0];self.assertEqual(r['maximum_display_decline_bb'],'80');self.assertTrue(r['priority_review']);self.assertIsNone(r['conditional_net_bb']);self.assertEqual(len(r['display_increases']),1)
    def test_equal_threshold(self):self.assertFalse(triage(fixture(('100','70','100','100')))['rows'][0]['priority_review'])
    def test_missing(self):self.assertIsNone(triage(fixture((None,'70',None,None)))['rows'][0]['maximum_display_decline_bb'])
    def test_rebuy(self):
        r=fixture();d=declaration(r,[{'file':r['segments'][0]['frames'][2]['file'],'kind':'rebuy','bb':'80'}]);a=reconcile(r,d)['reviews'][0];self.assertEqual(a['conditional_net_bb'],'-80');self.assertTrue(a['conditional_loss_over_30bb']);self.assertFalse(a['financial_result_verified'])
    def test_win_not_loss(self):
        r=fixture(('100','50','170','170'));self.assertEqual(reconcile(r,declaration(r))['reviews'][0]['conditional_net_bb'],'70')
    def test_incomplete(self):
        r=fixture();self.assertIsNone(reconcile(r,declaration(r,complete=False))['reviews'][0]['conditional_net_bb'])
    def test_wrong_anchor(self):
        r=fixture();d=declaration(r);d['reviews'][0]['after']['bb']='99'
        with self.assertRaisesRegex(ValueError,'Anchor disagrees'):reconcile(r,d)
    def test_wrong_review(self):
        r=fixture();d=declaration(r);d['review_sha256']='0'*64
        with self.assertRaises(ValueError):reconcile(r,d)
    def test_duplicate_transfer(self):
        r=fixture();t={'file':r['segments'][0]['frames'][2]['file'],'kind':'rebuy','bb':'80'}
        with self.assertRaisesRegex(ValueError,'Duplicate'):reconcile(r,declaration(r,[t,t]))
    def test_withdrawal(self):
        r=fixture(('100','100','80','80'));d=declaration(r,[{'file':r['segments'][0]['frames'][2]['file'],'kind':'withdrawal','bb':'20'}]);self.assertEqual(reconcile(r,d)['reviews'][0]['conditional_net_bb'],'0')
if __name__=='__main__':unittest.main()
