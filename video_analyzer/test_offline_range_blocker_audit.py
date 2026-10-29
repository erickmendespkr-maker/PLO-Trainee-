"""Synthetic preflight tests; no real video or opponent ranges are claimed."""
import copy
import unittest

from offline_range_blocker_audit import audit


HERO5 = ['As', 'Ks', 'Qh', 'Jh', 'Tc']
BOARD = ['2c', '3d', '4h', '5s', '6c']
LEGAL = ['7c', '8d', '9h', 'Td', 'Jc']
BLOCKED = ['As', '8d', '9h', 'Td', 'Jc']
OTHER = ['7d', '8c', '9s', 'Th', 'Jd']


def hypothesis(call=None, raised=None):
    return [{'label': 'reviewer hypothesis',
             'call_model': call or {'kind': 'uniform'},
             'raise_called_model': raised or {'kind': 'uniform'}}]


def weighted(*combos):
    return {'kind': 'weighted_combos', 'combos':
            [{'cards': list(hand), 'weight': weight} for hand, weight in combos]}


class RangeAuditTests(unittest.TestCase):
    def run_audit(self, hs):
        return audit('PLO5', HERO5, BOARD, hs)

    def test_uniform_not_observed(self):
        row = self.run_audit(hypothesis())['rows'][0]
        self.assertIsNone(row['call']['blocked_weight_fraction'])
        self.assertFalse(row['call']['range_accuracy_verified'])

    def test_blocked_mass_and_renormalization_warning(self):
        row = self.run_audit(hypothesis(weighted((LEGAL, 1), (BLOCKED, 3))))['rows'][0]
        self.assertEqual(row['call']['blocked_combos'], 1)
        self.assertEqual(row['call']['eligible_combos'], 1)
        self.assertAlmostEqual(row['call']['blocked_weight_fraction'], .75)
        self.assertIn('renormalized', row['call']['warning'])

    def test_all_blocked_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no legal combos'):
            self.run_audit(hypothesis(weighted((BLOCKED, 1))))

    def test_wrong_variant_rejected(self):
        with self.assertRaises(ValueError):
            self.run_audit(hypothesis(weighted((LEGAL + ['Qc'], 1))))

    def test_duplicate_permutation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.run_audit(hypothesis(weighted((LEGAL, 1), (list(reversed(LEGAL)), 2))))

    def test_disjoint_conditional_ranges_allowed_and_disclosed(self):
        row = self.run_audit(hypothesis(weighted((LEGAL, 1)), weighted((OTHER, 1))))['rows'][0]
        self.assertEqual(row['eligible_combo_overlap_count'], 0)
        self.assertIn('Disjoint', row['warning'])

    def test_overlap_count(self):
        row = self.run_audit(hypothesis(weighted((LEGAL, 1), (OTHER, 1)),
                                       weighted((LEGAL, 2))))['rows'][0]
        self.assertEqual(row['eligible_combo_overlap_count'], 1)

    def test_fingerprint_independent_of_key_order(self):
        m = weighted((LEGAL, 1))
        n = {'combos': copy.deepcopy(m['combos']), 'kind': 'weighted_combos'}
        x = self.run_audit(hypothesis(m))['rows'][0]['call']['model_sha256']
        y = self.run_audit(hypothesis(n))['rows'][0]['call']['model_sha256']
        self.assertEqual(x, y)
        self.assertEqual(len(x), 64)

    def test_no_input_mutation(self):
        hs = hypothesis(weighted((LEGAL, 1), (BLOCKED, 3)))
        before = copy.deepcopy(hs)
        self.run_audit(hs)
        self.assertEqual(hs, before)

    def test_duplicate_hero_board_rejected(self):
        with self.assertRaises(ValueError):
            audit('PLO5', HERO5, ['As', '3d', '4h'], hypothesis())

    def test_invalid_weight_rejected(self):
        for weight in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                self.run_audit(hypothesis(weighted((LEGAL, weight))))

    def test_six_card_range(self):
        legal6 = LEGAL + ['Qc']
        result = audit('PLO6', HERO5 + ['9d'], BOARD,
                       hypothesis(weighted((legal6, 1))))
        self.assertEqual(result['rows'][0]['call']['eligible_combos'], 1)


if __name__ == '__main__':
    unittest.main()
