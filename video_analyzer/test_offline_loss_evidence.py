import unittest
from offline_loss_evidence import classify_hand_evidence as classify
BASE=dict(hand_id="h1",table_id=1,hero_invested_bb=35,fold_visible=True,fold_human_verified=True,investment_human_verified=True)
class TestLossEvidence(unittest.TestCase):
    def test_fold(self): self.assertEqual(classify(BASE)["confirmed_loss_bb"],35)
    def test_unverified_fold(self): self.assertIsNone(classify({**BASE,"fold_human_verified":False})["confirmed_loss_bb"])
    def test_unverified_investment(self): self.assertIsNone(classify({**BASE,"investment_human_verified":False})["confirmed_loss_bb"])
    def test_threshold(self): self.assertFalse(classify({**BASE,"hero_invested_bb":30})["loss_over_30bb"])
    def test_stack_loss(self): self.assertEqual(classify({**BASE,"fold_visible":False,"stack_before_bb":100,"stack_after_bb":55,"stack_adjustments_bb":0,"stack_human_verified":True})["confirmed_loss_bb"],45)
    def test_rebuy(self): self.assertEqual(classify({**BASE,"fold_visible":False,"stack_before_bb":100,"stack_after_bb":155,"stack_adjustments_bb":100,"stack_human_verified":True})["confirmed_loss_bb"],45)
    def test_missing_adjustment(self): self.assertIsNone(classify({**BASE,"fold_visible":False,"stack_before_bb":100,"stack_after_bb":55,"stack_human_verified":True})["confirmed_loss_bb"])
    def test_conflict(self): self.assertEqual(classify({**BASE,"stack_before_bb":100,"stack_after_bb":20,"stack_adjustments_bb":0,"stack_human_verified":True})["classification"],"CONFLICTING_EVIDENCE")
    def test_winning_hand(self): self.assertEqual(classify({**BASE,"fold_visible":False,"stack_before_bb":100,"stack_after_bb":120,"stack_adjustments_bb":0,"stack_human_verified":True})["classification"],"NO_CONFIRMED_LOSS")
    def test_invalid_investment(self):
        for n in (-1,float("nan"),True):
            with self.assertRaises(ValueError): classify({**BASE,"hero_invested_bb":n})
    def test_partial_stack(self):
        with self.assertRaises(ValueError): classify({**BASE,"stack_before_bb":100})
    def test_table(self):
        with self.assertRaises(ValueError): classify({**BASE,"table_id":5})
if __name__=="__main__": unittest.main()
