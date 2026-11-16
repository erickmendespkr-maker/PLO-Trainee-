"""Regression tests for conditional EV action envelopes."""
import unittest
from video_analyzer.offline_ev_action_envelopes import summarize_action_ev_scenarios as summarize

class ActionEnvelopeTests(unittest.TestCase):
    def test_strict_dominance(self):
        result = summarize([
            {'id':'tight','range_source':'manual tight','ev':{'fold':[0,0],'call':[3,4]}},
            {'id':'loose','range_source':'manual loose','ev':{'fold':[0,0],'call':[2,5]}}])
        self.assertEqual(result['robust_action'], 'call')
        self.assertEqual(result['ev_envelopes']['call'], [2,5])
        self.assertFalse(result['hand_error_verified'])

    def test_overlap_not_robust(self):
        result = summarize([{'id':'a','range_source':'hypothesis','ev':{'fold':[0,0],'call':[-1,2]}}])
        self.assertTrue(result['range_sensitive'])
        self.assertIsNone(result['robust_action'])

    def test_reversal_across_ranges(self):
        result = summarize([
            {'id':'a','range_source':'one','ev':{'fold':[0,0],'call':[2,3]}},
            {'id':'b','range_source':'two','ev':{'fold':[0,0],'call':[-3,-2]}}])
        self.assertTrue(result['range_sensitive'])

    def test_invalid_inputs(self):
        good = {'id':'a','range_source':'manual','ev':{'call':[0,1]}}
        invalid = [[], [good,good],
            [{'id':'a','range_source':'','ev':{'call':[0,1]}}],
            [{'id':'a','range_source':'manual','ev':{'call':[float('nan'),1]}}],
            [{'id':'a','range_source':'manual','ev':{'call':[2,1]}}],
            [{'id':'a','range_source':'manual','ev':{'bet':[0,1]}}],
            [good,{'id':'b','range_source':'manual','ev':{'fold':[0,0]}}]]
        for case in invalid:
            with self.subTest(case=str(case)), self.assertRaises(ValueError):
                summarize(case)

    def test_single_action_not_a_verdict(self):
        result = summarize([{'id':'a','range_source':'manual','ev':{'fold':[0,0]}}])
        self.assertIsNone(result['robust_action'])
        self.assertFalse(result['gto_solution'])

if __name__ == '__main__':
    unittest.main()
