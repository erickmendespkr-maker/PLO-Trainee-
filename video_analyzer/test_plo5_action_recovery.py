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
if __name__=='__main__':unittest.main()
