"""Synthetic checks for conservative offline evidence gate."""
import unittest
try:
    from .offline_review_evidence_gate import review_gate
except ImportError:
    from offline_review_evidence_gate import review_gate

def sample():
    return {"review_status":"HUMAN_CONFIRMED","game":"PLO5","table_id":1,
            "hand_start_seconds":2,"hand_end_seconds":12,
            "hero_cards":["As","Kh","Qd","Jc","Ts"],"board_cards":["2c","3d","4h"],
            "action":"call","pot_before_action":100,"amount_to_call":25,
            "evidence":[{"human_verified":True,"pts_seconds":5,"frame_sha256":"a"*64}],
            "range_assumptions":{"villain":"hypothetical"},
            "model_assumptions":{"rake":0}}

class EvidenceGateTests(unittest.TestCase):
    def test_reviewed_synthetic(self):
        result=review_gate(sample())
        self.assertEqual(result["status"],"CONDITIONAL_ANALYSIS_PERMITTED")
        self.assertFalse(result["gto_claim_permitted"])
        self.assertFalse(result["automatic_blunder_label_permitted"])
    def test_unreviewed(self):
        h=sample();h["review_status"]="AUTO_DETECTED"
        self.assertIn("human_review_missing",review_gate(h)["reasons"])
    def test_duplicate_card(self):
        h=sample();h["board_cards"][0]="As"
        self.assertIn("invalid_or_duplicate_cards",review_gate(h)["reasons"])
    def test_invalid_time(self):
        h=sample();h["hand_end_seconds"]=1
        self.assertIn("hand_interval_unverified",review_gate(h)["reasons"])
    def test_missing_range(self):
        h=sample();h["range_assumptions"]={}
        self.assertIn("opponent_range_missing",review_gate(h)["reasons"])
    def test_unverified_frame(self):
        h=sample();h["evidence"][0]["human_verified"]=False
        self.assertIn("frame_evidence_unverified",review_gate(h)["reasons"])
    def test_plo6(self):
        h=sample();h["game"]="PLO6";h["hero_cards"].append("9s")
        self.assertEqual(review_gate(h)["status"],"CONDITIONAL_ANALYSIS_PERMITTED")
    def test_nan(self):
        h=sample();h["amount_to_call"]=float("nan")
        self.assertIn("amount_to_call_unverified",review_gate(h)["reasons"])
    def test_invalid_input(self):
        with self.assertRaises(ValueError):review_gate(None)

if __name__=="__main__":
    unittest.main()
