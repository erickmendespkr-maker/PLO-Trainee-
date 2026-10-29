"""Synthetic tests for conditional terminal EV; no video/action inference."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from offline_conditional_action_ev import build


def example(variant='PLO5'):
    hero = ['As', 'Ks', 'Qh', 'Jh', 'Tc']
    if variant == 'PLO6':
        hero.append('9d')
    scenario = {'variant': variant, 'hero_cards': hero,
                'board_cards': ['2c', '3d', '4h', '5s', '6c'],
                'opponent_model': {'kind': 'uniform'},
                'iterations': 8, 'seed': 42, 'manual_review_confirmed': True}
    return {'call_scenario': copy.deepcopy(scenario),
            'raise_called_scenario': copy.deepcopy(scenario),
            'pot_now': 100, 'call_cost': 20, 'raise_extra': 40,
            'fold_probability_assumed': 0.35}


class ConditionalActionEVTests(unittest.TestCase):
    def test_variants_and_accounting(self):
        for variant in ('PLO5', 'PLO6'):
            with self.subTest(variant=variant):
                d = example(variant)
                r = build(d)
                e1 = r['call_scenario_equity']['equity']
                e2 = r['raise_called_scenario_equity']['equity']
                self.assertAlmostEqual(r['call_ev_incremental'], e1*120-20)
                self.assertAlmostEqual(r['raise_ev_incremental'],
                                       .35*100+.65*(e2*200-60))
                self.assertFalse(r['action_observed_or_graded'])
                self.assertFalse(r['ocr_semantics_verified'])

    def test_known_royal_flush_equity(self):
        d = example()
        for name in ('call_scenario', 'raise_called_scenario'):
            d[name]['hero_cards'] = ['As', 'Ks', '2h', '3h', '4d']
            d[name]['board_cards'] = ['Qs', 'Js', 'Ts', '5d', '6c']
        r = build(d)
        self.assertEqual(r['call_scenario_equity']['equity'], 1.0)
        self.assertEqual(r['raise_called_scenario_equity']['equity'], 1.0)
        self.assertEqual(r['call_ev_incremental'], 100.0)
        self.assertEqual(r['raise_ev_incremental'], 100.0 + (1-0.35)*40.0)

    def test_deterministic(self):
        self.assertEqual(build(example()), build(example()))

    def test_fold_probability_extremes(self):
        d = example()
        d['fold_probability_assumed'] = 1
        self.assertEqual(build(d)['raise_ev_incremental'], 100)
        d['fold_probability_assumed'] = 0
        r = build(d)
        self.assertAlmostEqual(r['raise_ev_incremental'],
                               r['raise_called_scenario_equity']['equity']*200-60)

    def test_ci_and_comparison_are_labeled(self):
        r = build(example())
        self.assertEqual(len(r['raise_ev_ci95_sampling_only_fixed_fold_probability']), 2)
        self.assertEqual(len(r['raise_minus_call_interval_from_marginal_bounds_not_joint_ci']), 2)
        self.assertTrue(r['range_models_are_reviewer_assumptions'])
        self.assertTrue(r['fold_probability_is_reviewer_assumption'])
        self.assertIn('not advice', r['warning'])

    def test_distinct_ranges_and_seeds(self):
        d = example()
        d['raise_called_scenario']['seed'] = 9
        d['raise_called_scenario']['opponent_model'] = {
            'kind': 'weighted_combos',
            'combos': [{'cards': ['7c', '8d', '9h', 'Ts', 'Jc'], 'weight': 1}]}
        r = build(d)
        self.assertEqual(r['raise_called_scenario_equity']['opponent_model_kind'], 'weighted_combos')
        self.assertEqual(r['call_scenario_equity']['opponent_model_kind'], 'uniform')

    def test_mismatch_rejected(self):
        for field, value in [('variant', 'PLO6'), ('hero_cards', ['7s']*5),
                             ('board_cards', ['2d', '3d', '4h', '5s', '6c'])]:
            d = example()
            d['raise_called_scenario'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(d)

    def test_invalid_numbers(self):
        for field, value in [('pot_now', 0), ('call_cost', -1), ('call_cost', 101),
                             ('raise_extra', 0), ('raise_extra', math.inf),
                             ('fold_probability_assumed', -0.1),
                             ('fold_probability_assumed', 1.01),
                             ('fold_probability_assumed', True),
                             ('pot_now', '100'), ('raise_extra', 1e12)]:
            d = example()
            d[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                build(d)

    def test_unsafe_or_unreviewed_scenarios(self):
        for key, value in [('manual_review_confirmed', False),
                           ('pot_now', 20), ('call_cost', 10),
                           ('iterations', 1)]:
            d = example()
            d['call_scenario'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build(d)

    def test_unexpected_fields(self):
        d = example()
        d['action_graded'] = True
        with self.assertRaises(ValueError):
            build(d)
        d = example()
        d['raise_called_scenario']['ocr_verified'] = True
        with self.assertRaises(ValueError):
            build(d)

    def test_cli_new_file_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, dest = root/'review.json', root/'ev.json'
            src.write_text(json.dumps(example()), encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('offline_conditional_action_ev.py')),
                   str(src), str(dest)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['action_graded'])
            self.assertEqual(json.loads(dest.read_text())['schema_version'], 1)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True, timeout=25).returncode, 0)


if __name__ == '__main__':
    unittest.main()
