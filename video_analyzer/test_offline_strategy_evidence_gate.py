"""Regression tests for fail-closed strategy evidence eligibility."""
import unittest
from offline_strategy_evidence_gate import assess

def example():
    return dict(video_sha256="a"*64,table_id="t1",hand_id="h1",start_pts=10.0,end_pts=20.0,
        hero_cards=["Ac","Kd","Qh","Js","Tc"],board_cards=["2c","3d","4h"],action="call",
        pot_before=100,call_cost=40,ranges={"villain":"hypothetical"},
        equity_seed=42,equity_trials=10000,equity_ci_low=.35,equity_ci_high=.40,
        human_reviewed=True,cards_visibility_confirmed=True,action_amounts_confirmed=True,
        model_assumptions_reviewed=True,variant="PLO5")

class GateTests(unittest.TestCase):
    def test_conditional_only(self):
        self.assertEqual(assess(example())["status"],"CONDITIONAL_REVIEW_ONLY")
    def test_unreviewed(self):
        x=example();x["human_reviewed"]=False
        self.assertFalse(assess(x)["eligible"])
    def test_duplicate_card(self):
        x=example();x["board_cards"][0]="Ac"
        self.assertIn("invalid_cards",assess(x)["reasons"])
    def test_bool_seed(self):
        x=example();x["equity_seed"]=True
        self.assertIn("invalid_equity_seed",assess(x)["reasons"])
    def test_nan(self):
        x=example();x["equity_ci_low"]=float("nan")
        self.assertFalse(assess(x)["eligible"])
    def test_reverse_pts(self):
        x=example();x["start_pts"]=30
        self.assertIn("invalid_pts_order",assess(x)["reasons"])
    def test_range_sensitive(self):
        x=example();x["range_sensitive"]=True
        self.assertFalse(assess(x)["eligible"])
    def test_plo6(self):
        x=example();x["variant"]="PLO6";x["hero_cards"].append("9c")
        self.assertTrue(assess(x)["eligible"])
    def test_no_record(self):
        self.assertFalse(assess(None)["eligible"])
    def test_no_ranges(self):
        x=example();x["ranges"]={}
        self.assertIn("missing_ranges",assess(x)["reasons"])

if __name__=="__main__": unittest.main()
