import unittest
from video_analyzer.offline_ev_decision_report import decision_report

class DecisionReportTests(unittest.TestCase):
    def setUp(self):
        self.s = {
            'tight': {'fold': (0, 0), 'call': (2, 3), 'raise': (1, 1.5)},
            'loose': {'fold': (0, 0), 'call': (1.5, 2.5), 'raise': (0.5, 1)},
        }

    def test_regret_and_overlap(self):
        r = decision_report(self.s, 'raise', unit='bb', assumptions={'rake': 0})
        self.assertIsNone(r['robust_action'])
        self.assertEqual(r['ev_loss']['overall_min_ev_loss'], 0.5)
        self.assertFalse(r['gto_solution'])

    def test_robust_winner(self):
        self.s['tight']['call'] = (4, 5)
        self.s['loose']['call'] = (4, 5)
        self.assertEqual(decision_report(self.s, 'raise', unit='bb', assumptions={'rake': 0})['robust_action'], 'call')

    def test_overlap(self):
        s = {'a': {'fold': (0, 0), 'call': (-1, 1)},
             'b': {'fold': (0, 0), 'call': (-2, 2)}}
        self.assertEqual(decision_report(s, 'call', unit='chips', assumptions={'range': 'unknown'})['status'], 'RANGE_SENSITIVE')

    def test_review_does_not_verify(self):
        r = decision_report(self.s, 'call', unit='bb', assumptions={'rake': 0}, hand_reviewed=True)
        self.assertFalse(r['visual_hand_verified_by_this_module'])
        self.assertTrue(r['publication_requires_external_review_binding'])

    def test_scenario_order(self):
        self.assertEqual(decision_report(self.s, 'fold', unit='bb', assumptions={'rake': 0})['scenario_ids'], ['tight', 'loose'])

    def test_missing_assumptions(self):
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='bb', assumptions={})

    def test_bad_units(self):
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='USD', assumptions={'rake': 0})

    def test_nan_assumption(self):
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='bb', assumptions={'rake': float('nan')})

    def test_mismatched_actions(self):
        self.s['loose'].pop('raise')
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='bb', assumptions={'rake': 0})

    def test_invalid_bounds(self):
        self.s['tight']['call'] = (float('inf'), float('inf'))
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='bb', assumptions={'rake': 0})

    def test_non_boolean_review(self):
        with self.assertRaises(ValueError):
            decision_report(self.s, 'call', unit='bb', assumptions={'rake': 0}, hand_reviewed=1)

if __name__ == '__main__':
    unittest.main()
