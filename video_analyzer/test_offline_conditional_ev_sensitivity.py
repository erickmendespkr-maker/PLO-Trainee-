"""Synthetic, deterministic tests of offline conditional EV sensitivity."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from offline_conditional_ev_sensitivity import build
from test_offline_conditional_action_ev import example


def sample(variant='PLO5'):
    return {'hypotheses': [{'label': 'uniform', 'ev_input': example(variant)}],
            'fold_probabilities': [0, .35, 1]}


class SensitivityTests(unittest.TestCase):
    def test_two_variants(self):
        for variant in ('PLO5', 'PLO6'):
            with self.subTest(variant=variant):
                r = build(sample(variant))
                self.assertEqual(r['variant'], variant)
                self.assertEqual(len(r['hypotheses'][0]['points']), 3)
                self.assertFalse(r['action_observed_or_graded'])

    def test_grid_endpoints_and_formula(self):
        r = build(sample())
        h = r['hypotheses'][0]
        p0, pm, p1 = h['points']
        self.assertAlmostEqual(p1['raise_ev_incremental'], 100)
        self.assertAlmostEqual(pm['raise_ev_incremental'],
                               .35*100+.65*p0['raise_ev_incremental'])
        self.assertEqual(p0['call_ev_incremental'], p1['call_ev_incremental'])

    def test_marginal_interval_order(self):
        for point in build(sample())['hypotheses'][0]['points']:
            lo, hi = point['raise_ev_ci95_sampling_only_fixed_ranges_and_fold_probability']
            self.assertLessEqual(lo, point['raise_ev_incremental']+1e-8)
            self.assertLessEqual(point['raise_ev_incremental'], hi+1e-8)
            self.assertEqual(len(point['raise_minus_call_bounds_from_marginals_not_joint_ci']), 2)

    def test_royal_flush_known_case(self):
        data = sample()
        ev = data['hypotheses'][0]['ev_input']
        for field in ('call_scenario', 'raise_called_scenario'):
            ev[field]['hero_cards'] = ['As', 'Ks', '2h', '3h', '4d']
            ev[field]['board_cards'] = ['Qs', 'Js', 'Ts', '5d', '6c']
        r = build(data)
        self.assertEqual(r['hypotheses'][0]['call_equity'], 1)
        self.assertEqual(r['hypotheses'][0]['raise_called_equity'], 1)
        self.assertEqual(r['hypotheses'][0]['points'][0]['raise_ev_incremental'], 140)
        self.assertEqual(r['hypotheses'][0]['points'][-1]['raise_ev_incremental'], 100)

    def test_multiple_range_hypotheses(self):
        data = sample()
        other = copy.deepcopy(data['hypotheses'][0]['ev_input'])
        other['raise_called_scenario']['opponent_model'] = {
            'kind': 'weighted_combos',
            'combos': [{'cards': ['7c', '8d', '9h', 'Ts', 'Jc'], 'weight': 1}]}
        data['hypotheses'].append({'label': 'tight', 'ev_input': other})
        r = build(data)
        self.assertEqual(len(r['hypotheses']), 2)
        self.assertEqual(r['hypotheses'][1]['raise_called_range_model'], 'weighted_combos')
        self.assertEqual(r['hypotheses'][0]['call_seed'], 42)

    def test_deterministic(self):
        self.assertEqual(build(sample()), build(sample()))

    def test_invalid_grid(self):
        for grid in ([], [0], [0, 0], [.5, .2], [0, 1.1], [0, -0.1],
                     [0, math.nan], [0, math.inf], [0, True],
                     [i/21 for i in range(22)]):
            data = sample()
            data['fold_probabilities'] = grid
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                build(data)

    def test_invalid_hypotheses(self):
        for hs in ([], [sample()['hypotheses'][0]]*6, 'bad'):
            d = sample()
            d['hypotheses'] = hs
            with self.assertRaises(ValueError):
                build(d)

    def test_duplicate_label_and_unsafe_label(self):
        for label in ('uniform', '<script>', 'bad\nlabel', 'x'*65):
            d = sample()
            d['hypotheses'].append({'label': label, 'ev_input': example()})
            with self.subTest(label=label), self.assertRaises(ValueError):
                build(d)

    def test_mismatched_pot_or_hand(self):
        for change in ('pot_now', 'hero_cards', 'variant'):
            d = sample()
            other = example()
            if change == 'pot_now':
                other['pot_now'] = 101
            elif change == 'hero_cards':
                other['call_scenario']['hero_cards'][0] = '7s'
                other['raise_called_scenario']['hero_cards'][0] = '7s'
            else:
                other = example('PLO6')
            d['hypotheses'].append({'label': 'other', 'ev_input': other})
            with self.subTest(change=change), self.assertRaises(ValueError):
                build(d)

    def test_unreviewed_input_rejected(self):
        d = sample()
        d['hypotheses'][0]['ev_input']['call_scenario']['manual_review_confirmed'] = False
        with self.assertRaises(ValueError):
            build(d)

    def test_unknown_keys_rejected(self):
        d = sample()
        d['observed_action'] = 'raise'
        with self.assertRaises(ValueError):
            build(d)

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/'in.json', Path(td)/'out.json'
            src.write_text(json.dumps(sample()), encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('offline_conditional_ev_sensitivity.py')),
                   str(src), str(dst)]
            run = subprocess.run(cmd, text=True, capture_output=True, timeout=25)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse(json.loads(run.stdout)['action_graded'])
            self.assertEqual(len(json.loads(dst.read_text())['hypotheses']), 1)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True, timeout=25).returncode, 0)


if __name__ == '__main__':
    unittest.main()
