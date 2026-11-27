import unittest
from plo5_pre_gto_tree import start
from plo5_action_reconstruct import infer

class ActionReconstructionTests(unittest.TestCase):
    def setUp(self):self.s=start({'SB':200,'BB':200},1,2)
    def test_unique_call_check(self):
        r=infer(self.s,{'SB':198,'BB':198},4,actor_known=True,target_actor=None,target_active=['SB','BB'])
        self.assertEqual(r['status'],'UNIQUE_WITHIN_STEP_LIMIT');self.assertEqual([x['action'] for x in r['candidates'][0]],['call','check']);self.assertFalse(r['actions_verified'])
    def test_ambiguous_without_actor(self):
        r=infer(self.s,{'SB':198,'BB':198},4)
        self.assertEqual(r['status'],'AMBIGUOUS');self.assertEqual(len(r['candidates']),2)
    def test_unique_fold(self):
        r=infer(self.s,{'SB':199,'BB':198},3,actor_known=True,target_actor=None,target_active=['BB'])
        self.assertEqual(r['status'],'UNIQUE_WITHIN_STEP_LIMIT');self.assertEqual(r['candidates'][0],[dict(position='SB',action='fold',amount=0)])
    def test_budget_no_path_and_invalid(self):
        self.assertEqual(infer(self.s,{'SB':198,'BB':198},4,max_nodes=1)['status'],'SEARCH_BUDGET_EXCEEDED')
        self.assertEqual(infer(self.s,{'SB':198,'BB':198},4,max_steps=0)['status'],'NO_PATH_WITHIN_STEP_LIMIT')
        with self.assertRaises(ValueError):infer(self.s,{'SB':200,'BB':198},2)
        with self.assertRaises(ValueError):infer(self.s,{'SB':198,'BB':198},5)

if __name__=='__main__':unittest.main()
