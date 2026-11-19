"""Regression checks for long offline sessions (no real video required)."""
import unittest
from .offline_loss_review_handoff import build_loss_review_handoff

FIELDS = ("hero_cards", "actions", "pot", "stacks", "hand_boundaries")

def proposal(i, invested=1):
    return {"hand_id": f"h{i}", "table_id": i % 4 + 1,
            "start_seconds": i, "end_seconds": i + .5,
            "hero_invested_bb": invested,
            "field_confidence": {key: .8 for key in FIELDS}}

def fold(i, amount):
    return {"hand_id": f"h{i}", "table_id": i % 4 + 1,
            "hero_invested_bb": amount, "fold_visible": True,
            "fold_human_verified": True, "investment_human_verified": True}

class ReviewPaginationTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_loss_review_handoff([], [])["total_proposals"], 0)
    def test_over_1000_preserved(self):
        result = build_loss_review_handoff([proposal(i) for i in range(1205)], [fold(1204, 40)])
        self.assertEqual(result["total_proposals"], 1205)
        self.assertEqual(result["confirmed_over_30bb"], 1)
        self.assertEqual(result["review_queue"][0]["hand_id"], "h1204")
    def test_cross_batch_duplicate_rejected(self):
        proposals = [proposal(i) for i in range(1001)]
        proposals[1000]["hand_id"] = "h0"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_loss_review_handoff(proposals, [])
    def test_orphan_rejected(self):
        with self.assertRaisesRegex(ValueError, "orphan"):
            build_loss_review_handoff([proposal(0)], [fold(1, 31)])
    def test_exact_30_not_over(self):
        self.assertEqual(build_loss_review_handoff([proposal(0, 30)], [fold(0, 30)])["confirmed_over_30bb"], 0)
    def test_limit(self):
        result = build_loss_review_handoff([proposal(i) for i in range(1200)], [], limit=3)
        self.assertEqual(len(result["review_queue"]), 3)
        self.assertEqual(result["total_proposals"], 1200)
    def test_no_ev_claim(self):
        result = build_loss_review_handoff([proposal(0)], [])
        self.assertFalse(result["analysis_verified"])
        self.assertFalse(result["review_queue"][0]["strategy_verified"])
    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            build_loss_review_handoff([], [], limit=True)

if __name__ == "__main__":
    unittest.main()
