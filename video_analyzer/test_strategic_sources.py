import unittest
import strategic_sources as s


class SourceTests(unittest.TestCase):
    def test_unique_ids(self):
        self.assertEqual(len({d.id for d in s.CATALOG}), len(s.CATALOG))

    def test_strategy_pending(self):
        for key in ('plospot-preflop', 'solvepoker-strategy'):
            plan = s.acquisition_plan(key, kind='strategy', variant=5)
            self.assertEqual(plan['status'], 'PERMISSION_PENDING')
            self.assertIsNone(plan['download_url'])
            self.assertFalse(plan['production_import_allowed'])

    def test_open_equity_scope(self):
        for key, variant, count in (('solvepoker-plo5-equity', 5, 134459),
                                    ('solvepoker-plo6-equity-top10000', 6, 10000)):
            plan = s.acquisition_plan(key, kind='equity', variant=variant)
            self.assertEqual(plan['status'], 'LICENSE_CANDIDATE')
            self.assertEqual(plan['advertised_rows'], count)
            self.assertEqual(plan['verified_rows'], 0)
            self.assertEqual(plan['license'], 'CC BY 4.0')
            self.assertEqual(plan['attribution'], 'solvepoker.app')
            self.assertFalse(plan['production_import_allowed'])

    def test_no_cross_scope(self):
        for key, kind, variant in (('solvepoker-plo5-equity', 'strategy', 5),
                                   ('solvepoker-plo5-equity', 'equity', 6),
                                   ('solvepoker-plo5-equity', 'equity', 5.0),
                                   ('plospot-preflop', 'strategy', 6),
                                   ('unknown', 'equity', 5)):
            with self.subTest(key=key, kind=kind, variant=variant), self.assertRaises(ValueError):
                s.acquisition_plan(key, kind=kind, variant=variant)


if __name__ == '__main__':
    unittest.main()
