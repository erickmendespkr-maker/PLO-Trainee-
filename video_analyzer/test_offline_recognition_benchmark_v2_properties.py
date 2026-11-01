"""Exhaustive small-case oracle for temporal maximum-cardinality matching."""
from random import Random
import unittest

from offline_recognition_benchmark_v2 import evaluate


def label(t):
    return {'table_id': 1, 'field': 'pot', 'timestamp': t, 'expected': 1}


def prediction(t):
    return {'table_id': 1, 'field': 'pot', 'timestamp': t,
            'parsed_candidate': 1, 'status': 'candidate_unverified'}


def exhaustive(gold, candidates, tolerance):
    def search(i, used):
        if i == len(gold):
            return 0
        best = search(i + 1, used)
        for j, stamp in enumerate(candidates):
            if not (used & (1 << j)) and abs(gold[i] - stamp) <= tolerance:
                best = max(best, 1 + search(i + 1, used | (1 << j)))
        return best
    return search(0, 0)


class TemporalMatchingPropertyTests(unittest.TestCase):
    def test_randomized_vs_exhaustive_oracle(self):
        rng = Random(263)
        for _ in range(1000):
            gold = sorted(rng.sample(range(30), rng.randint(0, 5)))
            candidates = sorted(rng.choices(range(30), k=rng.randint(0, 5)))
            tolerance = rng.choice([0, 1, 2, 5, 10])
            result = evaluate([prediction(t) for t in candidates],
                              [label(t) for t in gold],
                              tolerance_seconds=tolerance)
            self.assertEqual(result['summary']['correct'],
                             exhaustive(gold, candidates, tolerance))


if __name__ == '__main__':
    unittest.main()
