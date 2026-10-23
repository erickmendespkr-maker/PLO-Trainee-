"""Synthetic-only checks: no hidden cards, ranges or EV can be inferred."""
import json
from pathlib import Path
import tempfile
import unittest

from decision_snapshot import build_decision_snapshots, snapshots_json
from hand_history import Observation


def obs(table, t, action, hand='h1', confidence=.95, **kwargs):
    return Observation(table, t, action, confidence, hand, **kwargs)


class DecisionSnapshotTests(unittest.TestCase):
    def sample(self):
        return [
            obs(1, 0, 'hand_start', variant='PLO5',
                hero_cards=('As', 'Ks', '2d', '3c', '4h'), pot=100),
            obs(1, 2, 'board', board=('Qs', 'Js', 'Ts')),
            obs(1, 3, 'call', actor='hero', amount=50),
            obs(1, 4, 'board', board=('Qs', 'Js', 'Ts', '9h')),
            obs(1, 5, 'hand_end')]

    def test_prior_cards_only(self):
        task = build_decision_snapshots(self.sample())['tasks'][0]
        self.assertEqual(task['visible_hints_unverified']['board']['value'], ['Qs', 'Js', 'Ts'])
        self.assertEqual(task['visible_hints_unverified']['hero_cards']['value'], ['As', 'Ks', '2d', '3c', '4h'])
        self.assertFalse(task['ready_for_ev'])
        self.assertIn('opponent_range_requires_manual_input', task['blockers'])

    def test_same_timestamp_is_not_prior(self):
        items = [obs(1, 0, 'hand_start', variant='PLO5'),
                 obs(1, 1, 'board', board=('As', 'Kd', 'Qc')),
                 obs(1, 1, 'fold', actor='hero'), obs(1, 2, 'hand_end')]
        task = build_decision_snapshots(items)['tasks'][0]
        self.assertIsNone(task['visible_hints_unverified']['board'])

    def test_future_cards_not_used(self):
        items = [obs(1, 0, 'hand_start', variant='PLO6'),
                 obs(1, 1, 'raise', actor='hero'),
                 obs(1, 2, 'board', board=('As', 'Kd', 'Qc')),
                 obs(1, 3, 'hand_end')]
        self.assertIsNone(build_decision_snapshots(items)['tasks'][0]['visible_hints_unverified']['board'])

    def test_multitable_isolation(self):
        items = [obs(1, 0, 'hand_start', variant='PLO5', pot=99),
                 obs(2, 0, 'hand_start', 'h2', variant='PLO6', pot=11),
                 obs(1, 1, 'fold', actor='hero'),
                 obs(2, 1, 'call', 'h2', actor='hero')]
        tasks = build_decision_snapshots(items)['tasks']
        self.assertEqual([t['visible_hints_unverified']['pot']['value'] for t in tasks], [99, 11])

    def test_stale_and_low_confidence(self):
        items = [obs(1, 0, 'hand_start', variant='PLO5', pot=50,
                     field_confidence={'pot': .2}),
                 obs(1, 45, 'fold', actor='hero')]
        task = build_decision_snapshots(items)['tasks'][0]
        self.assertIn('pot_stale_observation', task['blockers'])
        self.assertIn('pot_low_subjective_confidence', task['blockers'])

    def test_audit_flags_preserved(self):
        items = [obs(1, 0, 'hand_start', variant='PLO5'),
                 obs(1, 1, 'call', actor='hero')]
        task = build_decision_snapshots(items)['tasks'][0]
        self.assertIn('missing_or_multiple_hand_end', task['hand_audit_flags'])
        self.assertIn('hand_consistency_flags_require_review', task['blockers'])

    def test_missing_actor_flag(self):
        self.assertIn('actor_not_confirmed', build_decision_snapshots(
            [obs(1, 0, 'fold')])['tasks'][0]['blockers'])

    def test_no_unassigned_hand_assumption(self):
        result = build_decision_snapshots([obs(1, 0, 'call', hand=None)])
        self.assertEqual(result['counts']['decisions'], 0)
        self.assertEqual(result['counts']['unassigned_observations'], 1)

    def test_validation(self):
        for kw in ({'min_confidence': True}, {'max_age_seconds': 0},
                   {'max_age_seconds': float('nan')}, {'min_confidence': 1.2}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                build_decision_snapshots([], **kw)
        with self.assertRaises(TypeError):
            build_decision_snapshots([{}])

    def test_reject_out_of_order(self):
        with self.assertRaisesRegex(ValueError, 'out of order'):
            build_decision_snapshots([obs(1, 2, 'fold'), obs(1, 1, 'call')])

    def test_json_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp)/'input.json', Path(tmp)/'output.json'
            inp.write_text(json.dumps([{'table_id': 1, 'timestamp': 1, 'action': 'fold',
                                        'confidence': .9, 'hand_id': 'h1'}]))
            self.assertEqual(snapshots_json(inp, out)['counts']['decisions'], 1)
            with self.assertRaises(ValueError):
                snapshots_json(inp, out)
            with self.assertRaises(ValueError):
                snapshots_json(inp, inp)

    def test_repeated_object_reference_rejected(self):
        event = obs(1, 1, 'fold')
        with self.assertRaisesRegex(ValueError, 'Repeated Observation'):
            build_decision_snapshots([event, event])

    def test_no_ready_for_ev_even_when_all_visible(self):
        task = build_decision_snapshots(self.sample())['tasks'][0]
        self.assertEqual(set(task['visible_hints_unverified']), {'board', 'hero_cards', 'pot'})
        self.assertFalse(task['human_confirmed'])
        self.assertEqual(task['observed_action_hint'], 'call')


if __name__ == '__main__':
    unittest.main()
