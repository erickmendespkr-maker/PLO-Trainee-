import unittest
from video_analyzer.offline_equity_ev_report import analyze,wilson_interval
HERO=['Ah','Kd','Qc','Js','Th']
BOARD=['2c','3d','4h']
def stub(payload):
    return {'runouts':10000,'exact':False,'players':[{'win':.27,'tie':.02,'equity':.28},{}]}
class TestReport(unittest.TestCase):
    def test_ev(self):
        r=analyze('PLO5',HERO,[[]],BOARD,90,30,evaluator=stub)
        self.assertAlmostEqual(r['conditional_call_ev']['call_ev_bb'],3.6)
        self.assertEqual(r['decision_status'],'REVIEW_REQUIRED')
    def test_ci(self):
        r=analyze('PLO5',HERO,[[]],BOARD,90,30,evaluator=stub)
        self.assertLess(r['win_probability_ci95'][0],.27)
        self.assertIsNone(r['equity_ci95'])
    def test_plo6(self):
        self.assertEqual(analyze('PLO6',HERO+['9d'],[[]],BOARD,90,30,evaluator=stub)['variant'],'PLO6')
    def test_invalid_cards(self):
        with self.assertRaises(ValueError):
            analyze('PLO5',HERO,[[]],['Ah','3d','4h'],90,30,evaluator=stub)
    def test_invalid_probabilities(self):
        def bad(p): return {'runouts':100,'players':[{'win':.9,'tie':.3,'equity':.95},{}]}
        with self.assertRaises(ValueError):
            analyze('PLO5',HERO,[[]],BOARD,90,30,evaluator=bad)
    def test_wilson(self):
        self.assertEqual(wilson_interval(0,100)[0],0)
        self.assertEqual(wilson_interval(1,100)[1],1)
if __name__=='__main__': unittest.main()
