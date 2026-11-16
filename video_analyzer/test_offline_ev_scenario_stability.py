import unittest
from offline_ev_scenario_stability import compare_scenarios


def s(i, fold, call, raise_):
    return {'id': str(i), 'range_source': 'synthetic range', 'ev': {'fold': fold, 'call': call, 'raise': raise_}}


class TestScenarioStability(unittest.TestCase):
    def test_stable(self):
        result = compare_scenarios([s(1, [0, 0], [2, 3], [-1, 1]), s(2, [0, 0], [4, 5], [-2, 1])])
        self.assertEqual(result['stable_action'], 'call')
        self.assertFalse(result['hand_error_verified'])
        self.assertFalse(result['gto_solution'])

    def test_range_flip(self):
        result = compare_scenarios([s(1, [0, 0], [2, 3], [-1, 1]), s(2, [0, 0], [-2, -1], [2, 3])])
        self.assertIsNone(result['stable_action'])
        self.assertTrue(result['range_sensitive_or_inconclusive'])

    def test_overlap(self):
        self.assertIsNone(compare_scenarios([s(1, [0, 0], [0, 2], [1, 3])])['stable_action'])

    def test_equal_boundary(self):
        self.assertIsNone(compare_scenarios([s(1, [0, 0], [1, 2], [2, 3])])['stable_action'])

    def test_reject_malformed(self):
        bad = [[], [s(1, [0, 0], [1, 2], [2, 3])]*1001,
               [s(1, [0, 0], [1, 2], [2, 3]), s(1, [0, 0], [1, 2], [2, 3])],
               [s(1, [0, 0], [float('nan'), 2], [2, 3])],
               [s(1, [0, 0], [3, 2], [2, 3])],
               [dict(s(1, [0, 0], [1, 2], [2, 3]), range_source='')]]
        for value in bad:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError):
                compare_scenarios(value)

    def test_different_actions(self):
        x = s(1, [0, 0], [1, 2], [2, 3])
        y = s(2, [0, 0], [1, 2], [2, 3])
        del y['ev']['raise']
        with self.assertRaises(ValueError):
            compare_scenarios([x, y])


if __name__ == '__main__':
    unittest.main()
