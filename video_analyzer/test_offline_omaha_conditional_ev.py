"""Deterministic synthetic tests of the offline conditional EV model."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_omaha_conditional_ev as ev


HERO5 = ['As', 'Kd', 'Qh', 'Jc', '9d']
HERO6 = HERO5 + ['8c']
BOARD = ['2c', '3d', '4h', '5s', '6c']
VILLAIN5 = ['7c', '7d', '8h', 'Th', 'Tc']
VILLAIN6 = VILLAIN5 + ['Jd']


def scenario(game='PLO5', *, seed=42):
    hero, villain = (HERO5, VILLAIN5) if game == 'PLO5' else (HERO6, VILLAIN6)
    return {'schema_version': 1, 'game_type': game, 'hero_hole': hero,
            'known_board': BOARD, 'explicit_villain_hands': [villain],
            'samples': 100, 'seed': seed, 'range_assumption': 'Synthetic exact opponent combination'}


def fixture(game='PLO5'):
    return {'schema_version': 1, 'decision_id': 'synthetic-table-1-hand-1',
            'source_note': 'Independent mathematical fixture, NOT observed video',
            'pot_before_decision': '100.00', 'call_cost': '20.00',
            'raise_total': '60.00', 'fold_probability': 0.25,
            'fold_probability_bounds': [0.1, 0.4],
            'call_scenario': scenario(game), 'raise_called_scenario': scenario(game, seed=17),
            'model_assumptions': {
                'heads_up_only': True,
                'terminal_showdown_after_call_or_raise_called': True,
                'no_side_pots': True, 'zero_rake': True,
                'pot_includes_opponent_current_bet': True,
                'ranges_and_fold_probability_are_hypotheses': True,
                'raise_legality_verified': False,
            }}


def mock_equity(eq, bounds=None):
    return {'game_type': 'PLO5', 'equity_estimate': eq,
            'equity_95pct_hoeffding_interval': bounds or [eq, eq]}


class ConditionalEvTests(unittest.TestCase):
    def test_call_raise_formulas_with_different_equities(self):
        # P=100, C=20, R=60, villain extra=40 => showdown pot=200.
        # call EV=.5*120-20=40; raise called EV=.25*200-60=-10;
        # raise EV=.25*100+.75*(-10)=17.50.
        with patch.object(ev.mc, 'estimate', side_effect=[mock_equity(.5), mock_equity(.25)]):
            r = ev.calculate(fixture())
        self.assertEqual((r['ev_fold'], r['ev_call'], r['ev_raise']),
                         ('0.00', '40.00', '17.50'))
        self.assertEqual(r['villain_extra_call_after_raise'], '40.00')
        self.assertFalse(r['action_recommendation_authorized'])

    def test_uncertainty_corners(self):
        with patch.object(ev.mc, 'estimate', side_effect=[mock_equity(.5, [.4, .6]),
                                                           mock_equity(.25, [.1, .5])]):
            r = ev.calculate(fixture())
        self.assertEqual(r['ev_call_sampling_bounds'], ['28.00', '52.00'])
        # e=.1 => called EV=-40, e=.5 => called EV=40.
        # min with f=.1 => -26; max f=.4 => 64.
        self.assertEqual(r['ev_raise_sampling_and_fold_assumption_bounds'],
                         ['-26.00', '64.00'])

    def test_fold_probability_one(self):
        s = fixture(); s['fold_probability'] = 1
        s['fold_probability_bounds'] = [1, 1]
        with patch.object(ev.mc, 'estimate', return_value=mock_equity(0)):
            r = ev.calculate(s)
        self.assertEqual(r['ev_raise'], '100.00')

    def test_fold_probability_zero(self):
        s = fixture(); s['fold_probability'] = 0
        s['fold_probability_bounds'] = [0, 0]
        with patch.object(ev.mc, 'estimate', return_value=mock_equity(0)):
            r = ev.calculate(s)
        self.assertEqual(r['ev_raise'], '-60.00')

    def test_deterministic_monte_carlo_plo5_and_plo6(self):
        for game in ('PLO5', 'PLO6'):
            with self.subTest(game=game):
                a, b = ev.calculate(fixture(game)), ev.calculate(fixture(game))
                self.assertEqual(a, b)
                self.assertEqual(a['game_type'], game)
                self.assertEqual(a['call_equity']['samples'], 100)
                self.assertEqual(a['raise_called_equity']['seed'], 17)

    def test_call_and_raise_ranges_must_match_snapshot(self):
        s = fixture(); s['raise_called_scenario']['known_board'] = ['2c', '3d', '4h']
        with self.assertRaisesRegex(ValueError, 'same visible snapshot'):
            ev.calculate(s)

    def test_mixed_game_blocked(self):
        s = fixture(); s['raise_called_scenario'] = scenario('PLO6')
        with self.assertRaisesRegex(ValueError, 'same visible snapshot'):
            ev.calculate(s)

    def test_zero_cost_blocked(self):
        s = fixture(); s['call_cost'] = '0'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_raise_must_exceed_call(self):
        s = fixture(); s['raise_total'] = '20'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_raise_above_conservative_pot_limit_blocked(self):
        s = fixture(); s['raise_total'] = '141'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_negative_pot_blocked(self):
        s = fixture(); s['pot_before_decision'] = '-1'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_call_exceeding_pot_blocked(self):
        s = fixture(); s['call_cost'] = '101'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_nan_and_infinity_blocked(self):
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(value=value):
                s = fixture(); s['pot_before_decision'] = value
                with self.assertRaises(ValueError): ev.calculate(s)

    def test_more_than_two_decimals_blocked(self):
        s = fixture(); s['pot_before_decision'] = '100.001'
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_boolean_amount_blocked(self):
        s = fixture(); s['call_cost'] = True
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_invalid_fold_bounds_blocked(self):
        for bounds in ([.5, .6], [.4, .2], [-.1, .4], [0, 1.1], [.1], '0..1'):
            with self.subTest(bounds=bounds):
                s = fixture(); s['fold_probability_bounds'] = bounds
                with self.assertRaises(ValueError): ev.calculate(s)

    def test_missing_assumption_blocked(self):
        s = fixture(); del s['model_assumptions']['zero_rake']
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_nonzero_rake_model_blocked(self):
        s = fixture(); s['model_assumptions']['zero_rake'] = False
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_false_no_future_betting_blocked(self):
        s = fixture(); s['model_assumptions']['terminal_showdown_after_call_or_raise_called'] = False
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_unsupported_raise_legality_claim_blocked(self):
        s = fixture(); s['model_assumptions']['raise_legality_verified'] = True
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_unknown_key_blocked(self):
        s = fixture(); s['auto_post_to_poker'] = True
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_missing_note_blocked(self):
        s = fixture(); s['source_note'] = ' '
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_duplicate_json_key_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; dst = Path(d) / 'out.json'
            src.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError): ev.process(src, dst)
            self.assertFalse(dst.exists())

    def test_output_exclusive_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; dst = Path(d) / 'out.json'
            src.write_text(json.dumps(fixture()))
            result = ev.process(src, dst)
            self.assertTrue(dst.exists())
            self.assertEqual(result['source_scenario_sha256'], ev.sha(src))
            with self.assertRaises(ValueError): ev.process(src, dst)
            self.assertEqual(json.loads(dst.read_text()), result)

    def test_output_must_not_overwrite_source(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; src.write_text(json.dumps(fixture()))
            with self.assertRaises(ValueError): ev.process(src, src)

    def test_symlink_input_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; src.write_text(json.dumps(fixture()))
            link = Path(d) / 'link.json'; link.symlink_to(src)
            with self.assertRaises(ValueError): ev.process(link, Path(d) / 'out.json')

    def test_symlink_output_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; src.write_text(json.dumps(fixture()))
            target = Path(d) / 'target.json'; link = Path(d) / 'out.json'
            link.symlink_to(target)
            with self.assertRaises(ValueError): ev.process(src, link)

    def test_input_too_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; src.write_bytes(b' ' * (ev.MAX_BYTES + 1))
            with self.assertRaises(ValueError): ev.process(src, Path(d) / 'out.json')

    def test_json_nan_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'source.json'; src.write_text('{"x":NaN}')
            with self.assertRaises(ValueError): ev.process(src, Path(d) / 'out.json')

    def test_equity_range_must_be_explicit(self):
        s = fixture(); s['call_scenario']['range_assumption'] = ''
        with self.assertRaises(ValueError): ev.calculate(s)

    def test_scenarios_require_real_omaha_cards(self):
        s = fixture(); s['call_scenario']['hero_hole'] = ['As', 'Kd']
        with self.assertRaises(ValueError): ev.calculate(s)


if __name__ == '__main__':
    unittest.main()
