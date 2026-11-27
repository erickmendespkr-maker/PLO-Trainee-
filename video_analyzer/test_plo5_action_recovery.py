import unittest
from plo5_pre_gto_tree import start,step
from plo5_action_recovery import recover

class RecoveryTests(unittest.TestCase):
    def setUp(self):self.s=start({'SB':200,'BB':200},1,2)
    def test_unique_call_check_with_fold_roster(self):
        r=recover(self.s,{'SB':198,'BB':198},4,folded={'SB':False,'BB':False},max_actions=1)
        self.assertEqual(r['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(r['candidates'],[[dict(position='SB',action='call',amount=1)]])
        self.assertFalse(r['action_verified'])
    def test_ambiguous_zero_payment(self):
        r=recover(self.s,{'SB':198,'BB':198},4,max_actions=2)
        self.assertEqual(r['status'],'AMBIGUOUS');self.assertEqual({len(p) for p in r['candidates']},{1,2})
    def test_fold_evidence(self):
        r=recover(self.s,{'SB':199,'BB':198},3,folded={'SB':True,'BB':False})
        self.assertEqual(r['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(r['candidates'][0][0]['action'],'fold')
    def test_budget_and_invalid(self):
        r=recover(self.s,{'SB':198,'BB':198},4,max_nodes=1);self.assertEqual(r['status'],'SEARCH_BUDGET_EXCEEDED')
        for remaining,pot in (({'SB':200,'BB':198},2),({'SB':198,'BB':198},3)):
            with self.assertRaises(ValueError):recover(self.s,remaining,pot)
        self.assertEqual(recover(self.s,{'SB':198,'BB':198},4,max_actions=0)['status'],'NO_MATCH_WITHIN_BOUNDS')
    def test_raise_payment(self):
        r=recover(self.s,{'SB':194,'BB':198},8,max_actions=1)
        self.assertEqual(r['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(r['candidates'][0][0],dict(position='SB',action='raise',amount=5))
    def test_actor_and_street_constraints(self):
        args=(self.s,{'SB':198,'BB':198},4)
        a=recover(*args,expected_actor='BB');self.assertEqual(a['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(len(a['candidates'][0]),1)
        b=recover(*args,expected_actor=None,expected_status='flop_transition');self.assertEqual(b['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(len(b['candidates'][0]),2)
        self.assertEqual(recover(*args,expected_actor='SB')['status'],'NO_MATCH_WITHIN_BOUNDS')
        with self.assertRaises(ValueError):recover(*args,expected_actor='BTN')
    def test_postflop_search(self):
        import plo5_post_gto_tree as post
        s=post.State(('BB','SB'),('2c','3d','4h'),4,(198,198),(0,0),(0,0),(False,False),(0,1),(-1,-1),(2,2),2,2)
        r=recover(s,{'BB':194,'SB':194},12,expected_actor=None,expected_status='chance_transition')
        self.assertEqual(r['status'],'AMBIGUOUS')
        self.assertTrue(all(sum(x['amount'] for x in seq)==8 for seq in r['candidates']))

if __name__=='__main__':unittest.main()
