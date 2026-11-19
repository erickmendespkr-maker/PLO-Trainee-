import unittest
from video_analyzer.offline_equity_uncertainty import equity_bound,conditional_call_ev_bound
class TestUncertainty(unittest.TestCase):
    def test_contains(self):
        r=equity_bound(.28,10000)
        self.assertLess(r["lower"],.28)
        self.assertGreater(r["upper"],.28)
    def test_more_trials(self):
        a=equity_bound(.5,100)
        b=equity_bound(.5,10000)
        self.assertGreater(a["upper"]-a["lower"],b["upper"]-b["lower"])
    def test_edges(self):
        self.assertEqual(equity_bound(0,100)["lower"],0)
        self.assertEqual(equity_bound(1,100)["upper"],1)
    def test_ev(self):
        r=conditional_call_ev_bound(90,30,.28,10000)
        self.assertAlmostEqual(r["call_ev_bb"],3.6)
        self.assertLess(r["call_ev_lower_bb"],3.6)
        self.assertGreater(r["call_ev_upper_bb"],3.6)
    def test_invalid_trials(self):
        for n in (0,-1,True,1.5):
            with self.subTest(n=n),self.assertRaises(ValueError): equity_bound(.5,n)
    def test_invalid_equity(self):
        for x in (-.1,1.1,float("nan"),True):
            with self.subTest(x=x),self.assertRaises(ValueError): equity_bound(x,100)
    def test_invalid_confidence(self):
        for x in (0,1,float("inf")):
            with self.subTest(x=x),self.assertRaises(ValueError): equity_bound(.5,100,x)
    def test_invalid_pot(self):
        with self.assertRaises(ValueError): conditional_call_ev_bound(10,20,.5,100)
