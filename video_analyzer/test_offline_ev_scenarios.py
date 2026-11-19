"""Synthetic regression cases for offline EV sensitivity."""
import unittest
from video_analyzer.offline_ev_scenarios import call_ev,range_sensitivity
class Tests(unittest.TestCase):
    def test_ev(self): self.assertAlmostEqual(call_ev(90,30,.28)["call_ev_bb"],3.6)
    def test_odds(self): self.assertAlmostEqual(call_ev(90,30,.28)["required_equity"],.25)
    def test_rake(self): self.assertAlmostEqual(call_ev(90,30,.5,.1)["call_ev_bb"],24)
    def test_positive(self): self.assertEqual(range_sensitivity(90,30,[{"range_label":"a","equity":.3}])["conclusion"],"POSITIVE_IN_ALL_SUPPLIED_SCENARIOS")
    def test_negative(self): self.assertEqual(range_sensitivity(90,30,[{"range_label":"a","equity":.1}])["conclusion"],"NEGATIVE_IN_ALL_SUPPLIED_SCENARIOS")
    def test_sensitive(self): self.assertEqual(range_sensitivity(90,30,[{"range_label":"a","equity":.1},{"range_label":"b","equity":.5}])["conclusion"],"SENSITIVE_TO_RANGE_ASSUMPTIONS")
    def test_nan(self):
        with self.assertRaises(ValueError): call_ev(90,30,float("nan"))
    def test_pot(self):
        with self.assertRaises(ValueError): call_ev(20,30,.5)
    def test_duplicate(self):
        with self.assertRaises(ValueError): range_sensitivity(90,30,[{"range_label":"a","equity":.1},{"range_label":"a","equity":.2}])
    def test_rake_one(self): self.assertIsNone(call_ev(90,30,.5,1)["required_equity"])
if __name__=="__main__": unittest.main()
