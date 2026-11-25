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


    def test_genius_restricted_by_variant(self):
        for variant in (5, 6):
            plan = s.acquisition_plan(f'plogenius-plo{variant}-strategy', kind='strategy', variant=variant)
            self.assertEqual(plan['status'], 'RESTRICTED')
            self.assertIsNone(plan['download_url'])
            self.assertFalse(plan['production_import_allowed'])
            self.assertEqual(plan['verified_rows'], 0)

    def test_mastermind_reference_only(self):
        for variant in (5, 6):
            key = f'plomastermind-plo{variant}-reference'
            plan = s.acquisition_plan(key, kind='reference', variant=variant)
            self.assertEqual(plan['status'], 'REFERENCE_ONLY')
            self.assertIsNone(plan['download_url'])
            self.assertIsNone(plan['license_url'])
            self.assertFalse(plan['production_import_allowed'])
            for kind in ('strategy', 'equity', 'heuristic'):
                with self.assertRaises(ValueError):
                    s.acquisition_plan(key, kind=kind, variant=variant)

    def test_mastermind_plo6_scope(self):
        plan = s.acquisition_plan('plomastermind-plo6-reference', kind='reference', variant=6)
        self.assertIn('postflop not released', plan['methodology'])
        self.assertIsNone(plan['advertised_rows'])
        with self.assertRaises(ValueError):
            s.acquisition_plan('plomastermind-plo6-reference', kind='reference', variant=5)

    def test_reference_never_becomes_download_candidate(self):
        from dataclasses import replace
        from unittest.mock import patch
        ref = next(d for d in s.CATALOG if d.id == 'plomastermind-plo5-reference')
        with patch.object(s, 'CATALOG', (replace(ref, restricted=False, license='CC BY 4.0',
                                               url='https://example.com/test.csv', attribution='fixture'),)):
            plan = s.acquisition_plan(ref.id, kind='reference', variant=5)
            self.assertEqual(plan['status'], 'REFERENCE_ONLY')
            self.assertIsNone(plan['download_url'])
            self.assertFalse(plan['production_import_allowed'])


    def test_rangeconverter_online_only(self):
        for variant in (5, 6):
            plan = s.acquisition_plan(f'rangeconverter-plo{variant}-strategy', kind='strategy', variant=variant)
            self.assertEqual(plan['status'], 'RESTRICTED')
            self.assertIsNone(plan['download_url'])
            self.assertFalse(plan['production_import_allowed'])
            self.assertIn('no range download', plan['distribution'])

    def test_plocom_reference_not_strategy(self):
        for variant in (5, 6):
            key = f'plocom-plo{variant}-reference'
            plan = s.acquisition_plan(key, kind='reference', variant=variant)
            self.assertEqual(plan['status'], 'REFERENCE_ONLY')
            self.assertIsNone(plan['download_url'])
            self.assertIn('range sampling unverified', plan['methodology'])
            for kind in ('strategy', 'equity'):
                with self.assertRaises(ValueError):
                    s.acquisition_plan(key, kind=kind, variant=variant)

    def test_complete_source_inventory(self):
        inventory = s.acquisition_inventory()
        self.assertEqual(len(inventory['providers']), 8)
        self.assertEqual(len(inventory['plans']), 18)
        self.assertEqual(inventory['advertised_candidate_rows'], 144459)
        self.assertFalse(inventory['production_import_enabled'])
        self.assertEqual(set(inventory['candidate_ids']),
                         {'solvepoker-plo5-equity', 'solvepoker-plo6-equity-top10000'})

    def test_inventory_never_counts_restricted_rows(self):
        from dataclasses import replace
        from unittest.mock import patch
        d = next(d for d in s.CATALOG if d.id == 'solvepoker-plo5-equity')
        with patch.object(s, 'CATALOG', (replace(d, restricted=True),)):
            inventory = s.acquisition_inventory()
            self.assertEqual(inventory['advertised_candidate_rows'], 0)
            self.assertEqual(inventory['candidate_ids'], [])


if __name__ == '__main__':
    unittest.main()
