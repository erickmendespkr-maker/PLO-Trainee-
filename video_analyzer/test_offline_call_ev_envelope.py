"""Synthetic regression tests for the independent conditional EV envelope."""
import unittest
from video_analyzer.offline_call_ev_envelope import call_ev_envelope

class TestEnvelope(unittest.TestCase):
    def test_zero_equity(self):
        self.assertEqual(call_ev_envelope(100, 50, [{"name":"a","equity_low":0,"equity_high":0}])["ev_low"], -50)
    def test_full_equity(self):
        self.assertEqual(call_ev_envelope(100, 50, [{"name":"a","equity_low":1,"equity_high":1}])["ev_high"], 100)
    def test_break_even(self):
        result = call_ev_envelope(100,50,[{"name":"a","equity_low":1/3,"equity_high":1/3}])
        self.assertAlmostEqual(result["ev_low"],0)
    def test_rake(self):
        self.assertEqual(call_ev_envelope(100,50,[{"name":"a","equity_low":1,"equity_high":1}],rake=10)["ev_high"],90)
    def test_sensitivity(self):
        x=call_ev_envelope(100,50,[{"name":"tight","equity_low":.2,"equity_high":.25},{"name":"loose","equity_low":.5,"equity_high":.6}])
        self.assertEqual(x["interpretation"],"range_sensitive_or_uncertain")
    def test_positive(self):
        self.assertEqual(call_ev_envelope(100,50,[{"name":"a","equity_low":.5,"equity_high":.6}])["interpretation"],"call_positive_all_scenarios")
    def test_negative(self):
        self.assertEqual(call_ev_envelope(100,50,[{"name":"a","equity_low":.1,"equity_high":.2}])["interpretation"],"fold_positive_all_scenarios")
    def test_invalid(self):
        for args in [(100,0,[{"name":"a","equity_low":0,"equity_high":1}]),(100,50,[]),(100,50,[{"name":"a","equity_low":.8,"equity_high":.3}]),(100,50,[{"name":"a","equity_low":float("nan"),"equity_high":1}])]:
            with self.subTest(args=args), self.assertRaises(ValueError): call_ev_envelope(*args)
    def test_duplicate_names(self):
        with self.assertRaises(ValueError): call_ev_envelope(100,50,[{"name":"a","equity_low":.2,"equity_high":.3}]*2)
    def test_no_gto(self):
        x=call_ev_envelope(100,50,[{"name":"a","equity_low":.5,"equity_high":.6}])
        self.assertFalse(x["gto_claim_permitted"])
        self.assertFalse(x["automatic_blunder_label_permitted"])

if __name__=="__main__": unittest.main()
