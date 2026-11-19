"""Regression tests for conservative offline fold evidence; synthetic only."""
import unittest
from video_analyzer.offline_fold_loss_evidence import OfflineFoldTracker, Observation, fold_label_candidate

class FoldEvidenceTests(unittest.TestCase):
    def test_fold_over_30_and_clip_ends_on_new_deal(self):
        t = OfflineFoldTracker("table1", 0)
        for x in [Observation(0,100), Observation(1,65), Observation(2,65),
                  Observation(3,fold_label=True), Observation(4,fold_label=True)]:
            t.feed(x)
        self.assertTrue(t.hand.loss_over_30bb)
        self.assertIsNone(t.hand.ended_pts)
        t.feed(Observation(5,new_deal=True))
        self.assertEqual(t.hand.ended_pts, 5)
    def test_absent_cards_not_fold(self):
        t = OfflineFoldTracker("a",0)
        t.feed(Observation(1,cards_visible=False))
        self.assertIsNone(t.hand.fold_pts)
    def test_single_fold_not_enough(self):
        t = OfflineFoldTracker("a",0)
        t.feed(Observation(1,fold_label=True))
        t.feed(Observation(2,fold_label=False))
        self.assertIsNone(t.hand.fold_pts)
    def test_exactly_30_not_over(self):
        t = OfflineFoldTracker("a",0)
        for x in [Observation(0,100),Observation(1,70),Observation(2,70),
                  Observation(3,fold_label=True),Observation(4,fold_label=True)]:
            t.feed(x)
        self.assertFalse(t.hand.loss_over_30bb)
    def test_no_duplicate_delta(self):
        t = OfflineFoldTracker("a",0)
        for x in [Observation(0,100),Observation(1,70),Observation(2,70),Observation(3,70)]:
            t.feed(x)
        self.assertEqual(t.hand.committed_bb,30)
    def test_two_investments(self):
        t = OfflineFoldTracker("a",0)
        for x in [Observation(0,100),Observation(1,80),Observation(2,80),
                  Observation(3,60),Observation(4,60)]:
            t.feed(x)
        self.assertEqual(t.hand.committed_bb,40)
    def test_ocr_gap_resets_baseline(self):
        t = OfflineFoldTracker("a",0)
        for x in [Observation(0,100),Observation(1),Observation(2,65),Observation(3,65)]:
            t.feed(x)
        self.assertEqual(t.hand.committed_bb,0)
        self.assertTrue(t.hand.incomplete_contributions)
    def test_stack_increase_not_loss(self):
        t = OfflineFoldTracker("a",0)
        for x in [Observation(0,100),Observation(1,120),Observation(2,120)]:
            t.feed(x)
        self.assertEqual(t.hand.committed_bb,0)
    def test_multi_table_isolation(self):
        a,b = OfflineFoldTracker("a",0),OfflineFoldTracker("b",0)
        for t in (a,b): t.feed(Observation(0,100))
        for x in [Observation(1,60),Observation(2,60),Observation(3,fold_label=True),Observation(4,fold_label=True)]: a.feed(x)
        self.assertTrue(a.hand.loss_over_30bb)
        self.assertFalse(b.hand.loss_over_30bb)
    def test_fold_ocr_token(self):
        self.assertTrue(fold_label_candidate(" FOLD "))
        self.assertFalse(fold_label_candidate("folder"))
    def test_invalid_pts(self):
        t = OfflineFoldTracker("a",2)
        with self.assertRaises(ValueError): t.feed(Observation(1))
    def test_nonfinite_stack(self):
        t = OfflineFoldTracker("a",0)
        with self.assertRaises(ValueError): t.feed(Observation(1,stack_bb=float("nan")))
    def test_no_observations_after_end(self):
        t = OfflineFoldTracker("a",0)
        t.feed(Observation(1,new_deal=True))
        with self.assertRaises(ValueError): t.feed(Observation(2))
    def test_stable_fold_timestamp(self):
        t = OfflineFoldTracker("a",0)
        t.feed(Observation(1,fold_label=True))
        t.feed(Observation(2,fold_label=True))
        self.assertEqual(t.hand.fold_pts,1)

if __name__ == "__main__":
    unittest.main()
