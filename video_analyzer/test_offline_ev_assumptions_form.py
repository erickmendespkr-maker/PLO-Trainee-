"""Synthetic validation, CLI and optional browser tests for the offline EV form."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_ev_assumptions_form import render, validate_assumptions, main


def config():
    return {'schema_version': 1, 'pot_now': 100, 'call_cost': 20,
            'raise_extra': 40, 'fold_probabilities': [0, .35, 1],
            'hypotheses': [{'label': 'uniforme', 'call_model': {'kind': 'uniform'},
                            'raise_called_model': {'kind': 'uniform'},
                            'call_iterations': 500, 'raise_called_iterations': 500,
                            'call_seed': 42, 'raise_called_seed': 43,
                            'fold_probability_assumed': .35}]}


class AssumptionsFormTests(unittest.TestCase):
    def setUp(self):
        self.data = config()

    def check_invalid(self):
        with self.assertRaises(ValueError):
            validate_assumptions(self.data)

    def test_valid(self):
        result = validate_assumptions(self.data)
        self.assertEqual(result['hypotheses'], 1)
        self.assertFalse(result['action_observed_or_graded'])

    def test_two_hypotheses(self):
        other = copy.deepcopy(self.data['hypotheses'][0])
        other['label'] = 'tight & speculative'
        self.data['hypotheses'].append(other)
        self.assertEqual(validate_assumptions(self.data)['hypotheses'], 2)

    def test_five_hypotheses_max(self):
        self.data['hypotheses'] = [dict(self.data['hypotheses'][0], label=f'range{i}')
                                   for i in range(5)]
        self.assertEqual(validate_assumptions(self.data)['hypotheses'], 5)
        self.data['hypotheses'].append(dict(self.data['hypotheses'][0], label='sixth'))
        self.check_invalid()

    def test_reject_cards_and_actions(self):
        for field in ('hero_cards', 'board_cards', 'observed_action',
                      'hero_identity_verified', 'manual_review_confirmed'):
            with self.subTest(field=field):
                self.data[field] = []
                self.check_invalid()
                del self.data[field]

    def test_reject_invalid_pot_geometry(self):
        for name, value in [('pot_now', 0), ('pot_now', 19),
                            ('call_cost', 0), ('raise_extra', -1),
                            ('raise_extra', float('inf')), ('pot_now', True)]:
            with self.subTest(name=name, value=value):
                saved = self.data[name]
                self.data[name] = value
                self.check_invalid()
                self.data[name] = saved
        self.data['pot_now'] = 1e9
        self.check_invalid()

    def test_reject_probability_grid(self):
        for values in ([], [0], [0, 0], [1, 0], [-.1, .5],
                       [0, float('nan')], [0, True], [i/21 for i in range(22)]):
            with self.subTest(values=values):
                self.data['fold_probabilities'] = values
                self.check_invalid()

    def test_reject_bad_labels(self):
        for value in ('', '<script>', 'bad\\name', 'x'*65, 'line\nbreak'):
            with self.subTest(value=value):
                self.data['hypotheses'][0]['label'] = value
                self.check_invalid()

    def test_reject_duplicate_labels(self):
        self.data['hypotheses'].append(copy.deepcopy(self.data['hypotheses'][0]))
        self.check_invalid()

    def test_reject_wrong_hypothesis_fields(self):
        self.data['hypotheses'][0]['verified_action'] = 'raise'
        self.check_invalid()

    def test_reject_bad_iterations_and_seeds(self):
        h = self.data['hypotheses'][0]
        for field, value in [('call_iterations', 1), ('raise_called_iterations', 50001),
                             ('call_seed', -1), ('raise_called_seed', 2**32),
                             ('call_seed', 4.5), ('call_iterations', True)]:
            with self.subTest(field=field, value=value):
                saved = h[field]
                h[field] = value
                self.check_invalid()
                h[field] = saved

    def test_reject_baseline_fold_probability(self):
        self.data['hypotheses'][0]['fold_probability_assumed'] = 1.1
        self.check_invalid()

    def test_valid_weighted_range(self):
        combo = {'cards': ['As', 'Ks', 'Qh', 'Jh', 'Tc'], 'weight': 1}
        self.data['hypotheses'][0]['call_model'] = {'kind': 'weighted_combos', 'combos': [combo]}
        self.assertEqual(validate_assumptions(self.data)['hypotheses'], 1)

    def test_reject_invalid_weighted_ranges(self):
        combo = {'cards': ['As', 'Ks', 'Qh', 'Jh', 'Tc'], 'weight': 1}
        h = self.data['hypotheses'][0]
        for model in ({'kind': 'uniform', 'combos': []},
                      {'kind': 'weighted_combos', 'combos': []},
                      {'kind': 'weighted_combos', 'combos': [combo, combo]},
                      {'kind': 'weighted_combos', 'combos': [dict(combo, weight=0)]},
                      {'kind': 'weighted_combos', 'combos': [dict(combo, cards=['As']*5)]},
                      {'kind': 'weighted_combos', 'combos': [dict(combo, cards=['As', 'Ks', 'Qh', 'Jh'])]},
                      {'kind': 'weighted_combos', 'combos': [dict(combo, cards=['As', 'Ks', 'Qh', 'Jh', 'Tc', '9d']), combo]}):
            with self.subTest(model=model):
                h['call_model'] = model
                self.check_invalid()

    def test_html_is_self_contained_and_no_external_resources(self):
        html = render()
        self.assertIn('Content-Security-Policy', html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn('ASSUMPTIONS.json', html)
        self.assertIn('fold_probabilities', html)
        self.assertNotIn('<script src=', html)
        self.assertNotIn('https://', html)
        self.assertNotIn('fetch(', html)
        self.assertNotIn('WebSocket', html)

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_js_syntax(self):
        html = render()
        js = html.split('<script>', 1)[1].split('</script>', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'form.js'
            path.write_text(js, encoding='utf-8')
            p = subprocess.run(['node', '--check', str(path)], capture_output=True,
                               text=True, timeout=15)
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_cli_create_verify_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'form.html'
            self.assertEqual(main(['create', str(out)]), 0)
            self.assertIn('hypotheses', out.read_text())
            with self.assertRaises(ValueError): main(['create', str(out)])
            src = Path(tmp)/'assumptions.json'
            src.write_text(json.dumps(self.data))
            self.assertEqual(main(['verify', str(src)]), 0)

    def test_cli_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/'assumptions.json'
            src.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError): main(['verify', str(src)])

    def test_cli_reject_symlink_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'original.html').write_text('original')
            (root/'form.html').symlink_to(root/'original.html')
            with self.assertRaises(ValueError): main(['create', str(root/'form.html')])
            self.assertEqual((root/'original.html').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
