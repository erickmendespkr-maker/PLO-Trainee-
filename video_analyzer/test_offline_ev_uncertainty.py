import unittest
from offline_ev_uncertainty import compare_actions

class UncertaintyTests(unittest.TestCase):
    def test_robust_action(self):
        r = compare_actions({'fold': [(0,0),(0,0)], 'call': [(2,3),(1,2)]})
        self.assertEqual(r['robust_action'], 'call')
        self.assertFalse(r['gto_solution'])
    def test_overlap_is_range_sensitive(self):
        r = compare_actions({'fold': [(0,0)], 'call': [(-1,1)]})
        self.assertEqual(r['status'], 'RANGE_SENSITIVE')
        self.assertIsNone(r['robust_action'])
    def test_scenario_count_mismatch(self):
        with self.assertRaises(ValueError):
            compare_actions({'fold': [(0,0)], 'call': [(1,2),(2,3)]})
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            compare_actions({'fold': [(0,0)], 'call': [(float('nan'),2)]})
    def test_inverted_rejected(self):
        with self.assertRaises(ValueError):
            compare_actions({'fold': [(0,0)], 'raise': [(3,2)]})
    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            compare_actions({'fold': [(0,0)], 'call': [(True,2)]})
    def test_missing_action_rejected(self):
        with self.assertRaises(ValueError):
            compare_actions({'fold': [(0,0)]})
    def test_envelope_across_scenarios(self):
        r=compare_actions({'fold': [(0,0),(0,0)], 'raise': [(5,6),(-2,-1)]})
        self.assertEqual(r['ev_envelopes']['raise'], (-2,6))
        self.assertEqual(r['status'], 'RANGE_SENSITIVE')

if __name__ == '__main__': unittest.main()
