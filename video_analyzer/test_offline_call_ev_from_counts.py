import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from offline_call_ev_from_counts import build, run, OUTCOME_STATUS, SAMPLING
import test_offline_math_decision_snapshot as fixtures


class CallEVTests(unittest.TestCase):
    def setUp(self):
        base = fixtures.DecisionSnapshotTests()
        base.setUp()
        self.candidate = base.build()
        self.outcomes = {
            'schema_version': 1, 'status': OUTCOME_STATUS,
            'source_candidate_sha256': 'a'*64, 'variant': 'PLO5',
            'seed': 42, 'trials': 500, 'wins': 200, 'ties': 100, 'losses': 200,
            'sampling': SAMPLING, 'omaha_exact_two_hole_three_board': True
        }

    def build(self):
        return build(self.candidate, self.outcomes, 'a'*64, 'b'*64)

    def test_ev_arithmetic(self):
        r = self.build()
        self.assertEqual(r['equity_estimate'], .5)
        self.assertEqual(r['ev_call_estimate'], 40)
        self.assertEqual(r['ev_fold'], 0)
        self.assertAlmostEqual(r['break_even_equity'], 1/6)
        self.assertIn('unverified', r['status'])

    def test_hoeffding_interval_contains_estimate(self):
        r = self.build()
        lo, hi = r['equity_95pct_hoeffding_interval']
        self.assertLess(lo, .5)
        self.assertGreater(hi, .5)
        self.assertAlmostEqual(hi - .5, math.sqrt(math.log(40)/1000))

    def test_all_losses(self):
        self.outcomes.update(wins=0, ties=0, losses=500)
        r = self.build()
        self.assertEqual(r['ev_call_estimate'], -20)
        self.assertEqual(r['equity_95pct_hoeffding_interval'][0], 0)

    def test_all_wins(self):
        self.outcomes.update(wins=500, ties=0, losses=0)
        r = self.build()
        self.assertEqual(r['ev_call_estimate'], 100)
        self.assertEqual(r['equity_95pct_hoeffding_interval'][1], 1)

    def test_all_ties(self):
        self.outcomes.update(wins=0, ties=500, losses=0)
        self.assertEqual(self.build()['equity_estimate'], .5)

    def test_wrong_candidate_hash(self):
        self.outcomes['source_candidate_sha256'] = 'b'*64
        with self.assertRaises(ValueError): self.build()

    def test_wrong_seed(self):
        self.outcomes['seed'] = 99
        with self.assertRaises(ValueError): self.build()

    def test_wrong_trials(self):
        self.outcomes['trials'] = 1000
        with self.assertRaises(ValueError): self.build()

    def test_bad_count_sum(self):
        self.outcomes['wins'] = 201
        with self.assertRaises(ValueError): self.build()

    def test_negative_count(self):
        self.outcomes['wins'] = -1
        self.outcomes['losses'] = 401
        with self.assertRaises(ValueError): self.build()

    def test_boolean_count(self):
        self.outcomes.update(wins=True, ties=99)
        with self.assertRaises(ValueError): self.build()

    def test_weighted_range_blocked(self):
        self.candidate['villain_combos'].append({'cards': ['8c','7h','6s','5d','4c'], 'weight': 2})
        with self.assertRaisesRegex(ValueError, 'nonuniform'):
            self.build()

    def test_wrong_variant(self):
        self.outcomes['variant'] = 'PLO6'
        with self.assertRaises(ValueError): self.build()

    def test_wrong_rules(self):
        self.outcomes['omaha_exact_two_hole_three_board'] = False
        with self.assertRaises(ValueError): self.build()

    def test_wrong_sampling(self):
        self.outcomes['sampling'] = 'weighted'
        with self.assertRaises(ValueError): self.build()

    def test_wrong_model(self):
        self.candidate['model'] = 'raise'
        with self.assertRaises(ValueError): self.build()

    def test_unscoped_candidate(self):
        self.candidate['status'] = 'reviewed_math_candidate_manual_ranges_not_computed'
        with self.assertRaises(ValueError): self.build()

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cp = d/'candidate.json'
            op = d/'outcomes.json'
            rp = d/'result.json'
            cp.write_text(json.dumps(self.candidate))
            self.outcomes['source_candidate_sha256'] = hashlib.sha256(cp.read_bytes()).hexdigest()
            op.write_text(json.dumps(self.outcomes))
            r = run(cp, op, rp)
            self.assertEqual(json.loads(rp.read_text()), r)
            with self.assertRaises(ValueError): run(cp, op, rp)


if __name__ == '__main__': unittest.main()
