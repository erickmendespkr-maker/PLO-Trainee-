import json
import tempfile
import unittest
from pathlib import Path
from temporal_consensus import aggregate_candidates, aggregate_json


def sample(t, value=50., confidence=.95, table=1, field='pot', status='candidate_unverified'):
    return {'table_id': table, 'timestamp': t, 'field': field,
            'parsed_candidate': value, 'mean_engine_confidence': confidence,
            'status': status}


class TemporalConsensusTests(unittest.TestCase):
    def test_three_repetitions_create_unverified_candidate(self):
        result = aggregate_candidates([sample(0), sample(1), sample(2)])
        self.assertEqual(len(result['stable_candidates']), 1)
        self.assertFalse(result['stable_candidates'][0]['human_confirmed'])
        self.assertTrue(result['requires_manual_review'])

    def test_conflicting_value_breaks_streak(self):
        result = aggregate_candidates([sample(0), sample(1), sample(2, 60), sample(3, 60)])
        self.assertEqual(len(result['stable_candidates']), 0)
        self.assertEqual(len(result['review_items']), 2)

    def test_duplicate_timestamps_not_independent(self):
        result = aggregate_candidates([sample(0), sample(0), sample(1)])
        self.assertEqual(len(result['stable_candidates']), 0)

    def test_low_confidence_breaks_streak(self):
        result = aggregate_candidates([sample(0), sample(1, confidence=.1), sample(2), sample(3)])
        self.assertEqual(len(result['stable_candidates']), 0)
        self.assertEqual(len(result['review_items']), 3)

    def test_separate_tables_and_fields(self):
        result = aggregate_candidates([sample(t, table=table, field=field) for table in (1, 2)
                                       for field in ('pot', 'bet') for t in (0, 1, 2)])
        self.assertEqual(len(result['stable_candidates']), 4)

    def test_large_gap_breaks_streak(self):
        result = aggregate_candidates([sample(0), sample(1), sample(10)])
        self.assertEqual(len(result['stable_candidates']), 0)

    def test_cards_as_list_supported(self):
        cards = ['As', 'Kd', 'Qc']
        result = aggregate_candidates([sample(t, value=cards, field='board') for t in (0, 1, 2)])
        self.assertEqual(result['stable_candidates'][0]['parsed_candidate'], cards)

    def test_invalid_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_candidates([sample(float('nan'))])

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_candidates([], min_engine_confidence=2)

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / 'in.json', Path(d) / 'out.json'
            src.write_text(json.dumps({'candidates': [sample(t) for t in (0, 1, 2)]}))
            aggregate_json(src, dst)
            self.assertEqual(len(json.loads(dst.read_text())['stable_candidates']), 1)


if __name__ == '__main__':
    unittest.main()
