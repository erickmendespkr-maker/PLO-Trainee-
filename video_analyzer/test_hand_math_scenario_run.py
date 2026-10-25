"""Synthetic PLO5/PLO6 tests: math is hypothetical and never video-verified."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from hand_math_intake import build
from hand_math_scenario_run import run, export


class HypotheticalMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h = {
            'schema_version': 1,
            'analysis_status': 'visual_verdicts_linked_to_unverified_hand_history_no_math',
            **{k: 'a' * 64 for k in ('recording_sha256', 'source_navigation_sha256',
                                    'source_review_sha256', 'source_gallery_sha256',
                                    'source_visual_verdicts_sha256')},
            'requires_manual_review': True,
            **{k: False for k in ('hand_boundaries_verified', 'cards_or_actions_verified',
                                  'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                                  'strategic_error_established')},
            'entries': [],
            'counts': {'spans': 4, 'annotations': 0, 'pending': 0, 'confirmed_visual': 0,
                       'rejected_visual': 0, 'uncertain': 0, 'unreviewable': 0},
        }
        for table in range(1, 5):
            h['entries'].append({'entry_id': f'table_{table}_span_0', 'table_id': table,
                                 'start_human_seconds': 1.0, 'end_human_seconds': 3.0,
                                 'contains_unresolved_interior_candidates': table == 3,
                                 'hand_reconstruction_verified': False,
                                 'ready_for_equity_or_ev': False, 'annotations': []})
        cls.intake = build(h, 'f' * 64)
        cls.hero5 = ['As', 'Ks', 'Qs', 'Js', 'Ts']
        cls.villain5 = ['2h', '3h', '4h', '6h', '7h']
        cls.board = ['2s', '3s', '4s', '5d', '9c']

    def setUp(self):
        self.completed = copy.deepcopy(self.intake)

    def fill(self, table=0, variant=5, action='call'):
        d = self.completed['tasks'][table]['manual_scenario_draft']
        d.update(timestamp=2.0, human_confirmed=True, observation_confidence=.85,
                 monte_carlo_trials=12, monte_carlo_seed=42,
                 model_notes='Synthetic test range, not inferred from video',
                 model_assumptions={'heads_up': True, 'all_in_no_future_betting': True,
                                    'no_rake': True, 'no_side_pots': True, 'no_icm': True,
                                    'hero_extra_chips': None, 'villain_extra_chips_if_called': None})
        hero = self.hero5 + (['8h'] if variant == 6 else [])
        villain = self.villain5 + (['8d'] if variant == 6 else [])
        for k, value in {'hero_cards': hero, 'board': self.board,
                         'observed_action': action, 'pot_before_action': 100,
                         'call_amount': 50}.items():
            d['reviewed_fields'][k] = {'value': value, 'confidence': .8,
                                       'source_timestamp': 2.0,
                                       'source': 'independent_manual_video_review',
                                       'human_confirmed': True}
        d['call_range'] = [{'cards': villain, 'weight': 1.0}]
        if action == 'raise':
            d['fold_probability'] = .2
            d['model_assumptions']['hero_extra_chips'] = 100
            d['model_assumptions']['villain_extra_chips_if_called'] = 50
        return d

    def calculate(self):
        return run(self.intake, self.completed, 'f' * 64)

    def test_empty_all_four_tables_skipped(self):
        result = self.calculate()
        self.assertEqual(result['counts'], {'total': 4, 'hypothetical': 0, 'blocked': 0, 'skipped': 4})
        self.assertFalse(result['ready_for_equity_or_ev'])

    def test_plo5_exact_showdown_and_call_ev(self):
        self.fill()
        result = self.calculate()
        one = result['results'][0]
        self.assertEqual(one['variant'], 'PLO5')
        self.assertEqual(one['equity'], 1)
        self.assertEqual(one['equity_sampling_ci95'], [1, 1])
        self.assertEqual(one['ev_vs_fold_zero'], 100)
        self.assertEqual(one['ev_sampling_ci95'], [100, 100])
        self.assertEqual(one['trials'], 12)
        self.assertEqual(one['seed'], 42)
        self.assertEqual(result['counts']['hypothetical'], 1)
        self.assertFalse(one['source_hand_reconstruction_verified'])
        self.assertFalse(one['strategic_error_established'])

    def test_plo6_raise_ev_and_fold_equity(self):
        self.fill(1, variant=6, action='raise')
        result = self.calculate()['results'][1]
        self.assertEqual(result['variant'], 'PLO6')
        self.assertEqual(result['ev_vs_fold_zero'], 140)
        self.assertEqual(result['observed_action_assumed'], 'raise')

    def test_repeatability_fixed_seed_and_partial_board(self):
        d = self.fill()
        d['reviewed_fields']['board']['value'] = self.board[:3]
        a, b = self.calculate(), self.calculate()
        self.assertEqual(a, b)
        one = a['results'][0]
        self.assertLessEqual(one['equity_sampling_ci95'][0], one['equity'])
        self.assertGreaterEqual(one['equity_sampling_ci95'][1], one['equity'])
        self.assertIn('sampling only', one['model_limitations'])

    def test_other_tables_do_not_contaminate(self):
        self.fill(0)
        self.fill(3, variant=6)
        result = self.calculate()
        self.assertEqual(result['counts']['hypothetical'], 2)
        self.assertEqual([r['table_id'] for r in result['results']], [1, 2, 3, 4])

    def test_protected_metadata_tamper_aborts(self):
        self.fill()
        for change in ('table', 'entry', 'status', 'hash', 'blockers', 'topflag'):
            data = copy.deepcopy(self.completed)
            task = data['tasks'][0]
            if change == 'table': task['table_id'] = 4
            if change == 'entry': task['entry_id'] = 'forged'
            if change == 'status': task['ready_for_equity_or_ev'] = True
            if change == 'hash': data['recording_sha256'] = 'b' * 64
            if change == 'blockers': task['blocking_reasons'] = []
            if change == 'topflag': data['automatic_clip_selection_authorized'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                run(self.intake, data, 'f' * 64)

    def test_manual_confirmation_missing_blocks(self):
        d = self.fill()
        d['human_confirmed'] = False
        self.assertEqual(self.calculate()['results'][0]['status'], 'blocked_invalid_manual_scenario')

    def test_each_required_field_is_mandatory(self):
        for field in ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount'):
            self.completed = copy.deepcopy(self.intake)
            d = self.fill()
            d['reviewed_fields'][field]['human_confirmed'] = False
            with self.subTest(field=field):
                self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_invalid_range_and_card_collision(self):
        for mode in ('collision', 'duplicate', 'no_range', 'bad_weight', 'bad_count'):
            self.completed = copy.deepcopy(self.intake)
            d = self.fill()
            if mode == 'collision': d['call_range'][0]['cards'][0] = 'As'
            if mode == 'duplicate': d['call_range'].append(copy.deepcopy(d['call_range'][0]))
            if mode == 'no_range': d['call_range'] = []
            if mode == 'bad_weight': d['call_range'][0]['weight'] = True
            if mode == 'bad_count': d['reviewed_fields']['hero_cards']['value'] = self.hero5[:4]
            with self.subTest(mode=mode):
                self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_missing_all_in_model_or_false_claim(self):
        for mode in ('missing', 'not_all_in', 'rake', 'side_pot', 'future'):
            self.completed = copy.deepcopy(self.intake)
            d = self.fill()
            m = d['model_assumptions']
            if mode == 'missing': d.pop('model_assumptions')
            if mode == 'not_all_in': m['all_in_no_future_betting'] = False
            if mode == 'rake': m['no_rake'] = False
            if mode == 'side_pot': m['no_side_pots'] = False
            if mode == 'future': m['no_icm'] = False
            with self.subTest(mode=mode):
                self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_bad_timestamps_and_confidence(self):
        for key, value in (('timestamp', 10), ('timestamp', True),
                           ('observation_confidence', 1.5), ('monte_carlo_trials', 5001),
                           ('monte_carlo_seed', True)):
            self.completed = copy.deepcopy(self.intake)
            d = self.fill()
            d[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_unsupported_action(self):
        self.fill()['reviewed_fields']['observed_action']['value'] = 'fold'
        self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_inconsistent_raise_parameters(self):
        d = self.fill(action='raise')
        d['model_assumptions']['hero_extra_chips'] = 10
        self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_untrusted_source_label(self):
        self.fill()['reviewed_fields']['board']['source'] = 'ocr_auto'
        self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_export_json_digest_and_no_overwrite(self):
        self.fill()
        with tempfile.TemporaryDirectory() as tmp:
            a, b, out = (Path(tmp) / n for n in ('intake.json', 'filled.json', 'result.json'))
            a.write_text(json.dumps(self.intake))
            b.write_text(json.dumps(self.completed))
            result = export(a, b, out)
            self.assertEqual(result['source_intake_sha256'], hashlib.sha256(a.read_bytes()).hexdigest())
            self.assertEqual(json.loads(out.read_text()), result)
            with self.assertRaises(ValueError): export(a, b, out)

    def test_reject_symlink_input_and_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, link, out = (Path(tmp) / n for n in ('intake.json', 'filled.json', 'link.json', 'out.json'))
            a.write_text(json.dumps(self.intake))
            b.write_text(json.dumps(self.completed))
            link.symlink_to(a)
            with self.assertRaises(ValueError): export(link, b, out)
            a.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError): export(a, b, out)

    def test_reject_forged_authority_in_editable_draft(self):
        self.fill()['ready_for_equity_or_ev'] = True
        self.assertEqual(self.calculate()['counts']['blocked'], 1)

    def test_reject_untrusted_template(self):
        intake = copy.deepcopy(self.intake)
        intake['tasks'][0]['manual_scenario_draft']['human_confirmed'] = True
        with self.assertRaises(ValueError): run(intake, self.completed, 'f' * 64)

    def test_invalid_sha(self):
        with self.assertRaises(ValueError): run(self.intake, self.completed, 'bad')


if __name__ == '__main__':
    unittest.main()
