import unittest
from .offline_loss_review_handoff import build_loss_review_handoff

def proposal(name, table=1, invested=40, start=0):
    return dict(hand_id=name, table_id=table, start_seconds=start,
        end_seconds=start+10, hero_invested_bb=invested,
        field_confidence={k: 0.7 for k in
            ("hero_cards", "actions", "pot", "stacks", "hand_boundaries")})

def folded(name, table=1, invested=40):
    return dict(hand_id=name, table_id=table, hero_invested_bb=invested,
        fold_visible=True, fold_human_verified=True,
        investment_human_verified=True)

class HandoffTests(unittest.TestCase):
    def test_confirmed_first(self):
        r=build_loss_review_handoff([proposal("a", invested=100),proposal("b")],[folded("b")])
        self.assertEqual(r["review_queue"][0]["hand_id"],"b")
        self.assertEqual(r["confirmed_over_30bb"],1)
    def test_unknown(self):
        self.assertFalse(build_loss_review_handoff([proposal("a")],[])["review_queue"][0]["loss_over_30bb"])
    def test_threshold(self):
        self.assertEqual(build_loss_review_handoff([proposal("a",invested=30)],[folded("a",invested=30)])["confirmed_over_30bb"],0)
    def test_conflict(self):
        e=folded("a")
        e.update(stack_before_bb=100,stack_after_bb=100,stack_adjustments_bb=0,stack_human_verified=True)
        r=build_loss_review_handoff([proposal("a")],[e])
        self.assertFalse(r["review_queue"][0]["loss_over_30bb"])
    def test_orphan(self):
        with self.assertRaises(ValueError): build_loss_review_handoff([proposal("a")],[folded("b")])
    def test_duplicate(self):
        with self.assertRaises(ValueError): build_loss_review_handoff([proposal("a")],[folded("a"),folded("a")])
    def test_table_mismatch(self):
        with self.assertRaises(ValueError): build_loss_review_handoff([proposal("a")],[folded("a",table=2)])
    def test_no_strategy(self):
        r=build_loss_review_handoff([proposal("a")],[folded("a")])
        self.assertFalse(r["analysis_verified"])
        self.assertFalse(r["review_queue"][0]["strategy_verified"])
    def test_invalid_evidence(self):
        with self.assertRaises(ValueError): build_loss_review_handoff([proposal("a")],{})
    def test_deterministic(self):
        p=[proposal("a"),proposal("b",start=20)]
        self.assertEqual(build_loss_review_handoff(p,[folded("a")]),build_loss_review_handoff(p,[folded("a")]))
