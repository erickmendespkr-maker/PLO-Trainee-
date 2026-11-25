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


    def test_restricted_sources(self):
        restricted = [d for d in s.CATALOG if d.provider in ('PokerData', 'OmahaSolve')]
        self.assertEqual(len(restricted), 6)
        for d in restricted:
            for variant in d.variants:
                with self.subTest(dataset=d.id):
                    plan = s.acquisition_plan(d.id, kind=d.kind, variant=variant)
                    self.assertEqual(plan['status'], 'RESTRICTED')
                    self.assertIsNone(plan['download_url'])
                    self.assertIsNone(plan['license_url'])
                    self.assertFalse(plan['production_import_allowed'])
                    self.assertEqual(plan['verified_rows'], 0)
                    self.assertTrue(plan['terms_url'])
                    self.assertTrue(plan['methodology'])

    def test_heuristics_are_not_solver_data(self):
        for variant in (5, 6):
            key = f'omahasolve-plo{variant}-ranges'
            self.assertEqual(s.acquisition_plan(key, kind='heuristic', variant=variant)['kind'], 'heuristic')
            with self.assertRaises(ValueError):
                s.acquisition_plan(key, kind='strategy', variant=variant)
            with self.assertRaises(ValueError):
                s.acquisition_plan(key, kind='equity', variant=variant)

    def test_pokerdata_scope(self):
        for key in ('pokerdata-plo5-preflop', 'pokerdata-plo5-postflop'):
            with self.assertRaises(ValueError):
                s.acquisition_plan(key, kind='strategy', variant=6)
        plan = s.acquisition_plan('pokerdata-plo5-preflop', kind='strategy', variant=5)
        self.assertIn('1.2 BB ante', plan['methodology'])
        self.assertIn('JSON', plan['distribution'])

    def test_restriction_overrides_license_candidate(self):
        from dataclasses import replace
        from unittest.mock import patch
        candidate = next(d for d in s.CATALOG if d.id == 'solvepoker-plo5-equity')
        with patch.object(s, 'CATALOG', (replace(candidate, restricted=True),)):
            plan = s.acquisition_plan(candidate.id, kind='equity', variant=5)
            self.assertEqual(plan['status'], 'RESTRICTED')
            self.assertIsNone(plan['download_url'])


if __name__ == '__main__':
    unittest.main()
