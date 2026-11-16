"""Additional offline-only regression cases for conditional EV comparisons."""
import unittest

from offline_ev_scenario_stability import compare_scenarios


def case(ident, fold, call, raise_):
    return {'id': ident, 'range_source': 'synthetic assumption',
            'ev': {'fold': fold, 'call': call, 'raise': raise_}}


class TestScenarioStabilityEdges(unittest.TestCase):
    def test_order_independence(self):
        a = case('tight', [0, 0], [2, 3], [-1, 1])
        b = case('loose', [0, 0], [3, 4], [-2, 1])
        self.assertEqual(compare_scenarios([a, b])['stable_action'],
                         compare_scenarios([b, a])['stable_action'])

    def test_boundary_touch_is_not_strict_dominance(self):
        a = case('a', [0, 0], [1, 2], [2, 3])
        b = case('b', [0, 0], [4, 5], [-1, 1])
        result = compare_scenarios([a, b])
        self.assertIsNone(result['stable_action'])
        self.assertIsNone(result['scenarios'][0]['strict_winner'])

    def test_one_action_is_not_comparative_evidence(self):
        cases = [{'id': x, 'range_source': 'synthetic', 'ev': {'call': [1, 2]}}
                 for x in ('a', 'b')]
        result = compare_scenarios(cases)
        self.assertIsNone(result['stable_action'])
        self.assertTrue(result['range_sensitive_or_inconclusive'])

    def test_nonfinite_and_boolean_endpoints_rejected(self):
        for invalid in (float('inf'), -float('inf'), float('nan'), True, False):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compare_scenarios([case('a', [0, 0], [invalid, 2], [-1, 1])])

    def test_no_proven_error_or_gto_for_stable_action(self):
        a = case('a', [0, 0], [2, 3], [-1, 1])
        b = case('b', [0, 0], [3, 4], [-2, 1])
        result = compare_scenarios([a, b])
        self.assertEqual(result['stable_action'], 'call')
        self.assertEqual(result['status'], 'CONDITIONAL_ONLY')
        self.assertIs(result['hand_error_verified'], False)
        self.assertIs(result['gto_solution'], False)


if __name__ == '__main__':
    unittest.main()
