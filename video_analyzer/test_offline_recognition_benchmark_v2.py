import json
from pathlib import Path
import tempfile
import unittest

from offline_recognition_benchmark_v2 import evaluate, run, wilson


def gold(t, value=10, table=1, field='pot'):
    return {'table_id': table, 'field': field, 'timestamp': t, 'expected': value}


def pred(t, value=10, table=1, field='pot', status='candidate_unverified'):
    return {'table_id': table, 'field': field, 'timestamp': t,
            'parsed_candidate': value, 'status': status}


class EvaluationTests(unittest.TestCase):
    def test_all_correct(self):
        x = evaluate([pred(1), pred(2)], [gold(1), gold(2)])['summary']
        self.assertEqual((x['coverage'], x['strict_f1'], x['answered_accuracy']), (1, 1, 1))

    def test_wrong_counts_as_fp_and_fn(self):
        x = evaluate([pred(1, 5)], [gold(1)])['summary']
        self.assertEqual((x['incorrect'], x['strict_precision'], x['strict_recall']), (1, 0, 0))

    def test_unmatched_answered_is_false_positive(self):
        x = evaluate([pred(1), pred(9)], [gold(1)])['summary']
        self.assertEqual((x['unmatched_answered_predictions'], x['strict_precision'],
                          x['strict_recall']), (1, .5, 1))

    def test_unmatched_abstaining_is_not_false_positive(self):
        x = evaluate([pred(1), pred(9, None, status='abstained')], [gold(1)])['summary']
        self.assertEqual((x['unmatched_abstaining_predictions'], x['strict_precision']), (1, 1))

    def test_no_ground_truth_has_no_accuracy(self):
        x = evaluate([pred(1)], [])['summary']
        self.assertIsNone(x['strict_recall'])
        self.assertEqual(x['unmatched_answered_predictions'], 1)

    def test_empty_predictions_are_missing(self):
        x = evaluate([], [gold(1)])['summary']
        self.assertEqual((x['abstained_or_missing'], x['coverage']), (1, 0))
        self.assertIsNone(x['answered_accuracy_wilson95'])

    def test_abstention_not_correct(self):
        x = evaluate([pred(1, 10, status='needs_manual_review')], [gold(1)])['summary']
        self.assertEqual((x['abstained_or_missing'], x['strict_recall']), (1, 0))

    def test_cross_table_and_field(self):
        x = evaluate([pred(1, table=2), pred(1, field='bet')], [gold(1)])
        self.assertEqual(x['summary']['correct'], 0)
        self.assertEqual(len(x['by_table_field']), 3)

    def test_earliest_feasible_avoids_greedy_missing(self):
        # Nearest-first matching for first gold could steal only viable later pred.
        x = evaluate([pred(.0), pred(.6)], [gold(.4), gold(.9)], tolerance_seconds=.5)
        self.assertEqual(x['summary']['correct'], 2)
        self.assertEqual([d['prediction_index'] for d in x['details']], [0, 1])

    def test_one_prediction_not_reused(self):
        x = evaluate([pred(1)], [gold(1), gold(1.2)])['summary']
        self.assertEqual((x['correct'], x['abstained_or_missing']), (1, 1))

    def test_tolerance_boundary(self):
        x = evaluate([pred(1.5)], [gold(1)], tolerance_seconds=.5)
        self.assertEqual(x['summary']['correct'], 1)
        y = evaluate([pred(1.5)], [gold(1)], tolerance_seconds=.49)
        self.assertEqual(y['summary']['correct'], 0)

    def test_cards_are_compared_as_exact_lists(self):
        x = evaluate([pred(1, ['As', 'Kh'], field='hero_cards')],
                     [gold(1, ['Kh', 'As'], field='hero_cards')])['summary']
        self.assertEqual(x['incorrect'], 1)

    def test_duplicate_ground_truth_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], [gold(1), gold(1)])

    def test_invalid_bool_table_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([pred(1, table=True)], [])

    def test_invalid_bool_amount_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([pred(1, True)], [])

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], [gold(float('nan'))])

    def test_negative_tolerance_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], [], tolerance_seconds=-1)

    def test_confidence_not_used_as_probability(self):
        p = pred(1)
        p['confidence'] = .999
        x = evaluate([p], [gold(1)])
        self.assertFalse(x['ocr_engine_confidence_calibrated'])
        self.assertFalse(x['equity_ev_authorized'])

    def test_wilson_intervals(self):
        self.assertIsNone(wilson(0, 0))
        lo, hi = wilson(5, 10)
        self.assertTrue(0 < lo < .5 < hi < 1)
        self.assertLess(wilson(0, 10)[1], .3)

    def test_large_synthetic_group(self):
        n = 4000
        x = evaluate([pred(i) for i in range(n)], [gold(i) for i in range(n)])
        self.assertEqual(x['summary']['correct'], n)

    def test_atomic_file_output_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ocr, truth, output = (root / x for x in ('ocr.json', 'gold.json', 'result.json'))
            ocr.write_text(json.dumps({'candidates': [pred(1)]}))
            truth.write_text(json.dumps([gold(1)]))
            r = run(ocr, truth, output)
            self.assertEqual(r['summary']['correct'], 1)
            self.assertEqual(len(r['source_ocr_sha256']), 64)
            with self.assertRaises((ValueError, FileExistsError)):
                run(ocr, truth, output)
            self.assertEqual(json.loads(output.read_text())['summary']['correct'], 1)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ocr, truth, output = (root / x for x in ('ocr.json', 'gold.json', 'out.json'))
            ocr.write_text('{"candidates":[],"candidates":[]}')
            truth.write_text('[]')
            with self.assertRaises(ValueError):
                run(ocr, truth, output)
            self.assertFalse(output.exists())

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ocr, alias, truth, output = (root / x for x in ('ocr.json', 'alias.json', 'gold.json', 'out.json'))
            ocr.write_text('{"candidates":[]}')
            alias.symlink_to(ocr)
            truth.write_text('[]')
            with self.assertRaises(ValueError):
                run(alias, truth, output)


if __name__ == '__main__':
    unittest.main()
