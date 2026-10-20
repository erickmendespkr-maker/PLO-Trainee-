import unittest
from recognition_metrics import score_ocr


def gold(t, value=100, table=1, field='pot'):
    return {'table_id': table, 'field': field, 'timestamp': t, 'expected': value}


def pred(t, value=100, status='candidate_unverified', table=1, field='pot'):
    return {'table_id': table, 'field': field, 'timestamp': t, 'parsed_candidate': value, 'status': status}


class MetricsTests(unittest.TestCase):
    def test_correct_and_incorrect_separate(self):
        r = score_ocr([pred(1), pred(2, 50)], [gold(1), gold(2)])
        self.assertEqual((r['correct'], r['incorrect']), (1, 1))
        self.assertEqual(r['answered_accuracy'], .5)

    def test_missing_counts_as_abstention(self):
        r = score_ocr([], [gold(1)])
        self.assertEqual(r['abstained_or_missing'], 1)
        self.assertIsNone(r['answered_accuracy'])

    def test_explicit_abstention(self):
        r = score_ocr([pred(1, None, 'needs_manual_review')], [gold(1)])
        self.assertEqual(r['coverage'], 0)

    def test_one_prediction_not_reused(self):
        r = score_ocr([pred(1)], [gold(1), gold(1.3)])
        self.assertEqual((r['correct'], r['abstained_or_missing']), (1, 1))

    def test_cross_table_never_matches(self):
        r = score_ocr([pred(1, table=2)], [gold(1)])
        self.assertEqual(r['correct'], 0)
        self.assertEqual(r['unmatched_predictions'], 1)

    def test_time_tolerance(self):
        r = score_ocr([pred(2)], [gold(1)], tolerance_seconds=.2)
        self.assertEqual(r['coverage'], 0)

    def test_empty_truth_no_fake_accuracy(self):
        r = score_ocr([], [])
        self.assertIsNone(r['overall_accuracy'])

    def test_duplicate_gold_rejected(self):
        with self.assertRaises(ValueError):
            score_ocr([], [gold(1), gold(1)])

    def test_invalid_tolerance_rejected(self):
        with self.assertRaises(ValueError):
            score_ocr([], [], tolerance_seconds=float('nan'))

    def test_card_lists(self):
        cards = ['As', 'Kd', 'Qc']
        r = score_ocr([pred(1, cards, field='board')], [gold(1, cards, field='board')])
        self.assertEqual(r['correct'], 1)


if __name__ == '__main__':
    unittest.main()
