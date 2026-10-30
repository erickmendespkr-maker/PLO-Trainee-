"""Offline synthetic integration tests for reviewed queue -> actual Monte Carlo engine."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_reviewed_math_batch as batch
import offline_reviewed_hand_math_queue as queue


def fixture():
    from test_offline_reviewed_hand_math_queue import fixture as source_fixture
    plan, annotations = source_fixture()
    return queue.build(plan, annotations, 'a'*64, 'b'*64)


class MathBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'queue.json'
        self.output = self.root / 'results'
        self.write(fixture())

    def write(self, data):
        self.input.write_text(json.dumps(data), encoding='utf-8')

    def run_batch(self):
        return batch.run(self.input, self.output)

    def test_end_to_end_monte_carlo_and_ev(self):
        manifest = self.run_batch()
        self.assertEqual((manifest['eligible_executed'], manifest['blocked_not_executed']), (1, 1))
        result = json.loads((self.output / 'H001.equity.json').read_text())
        eq = result['equity_result']
        self.assertEqual(eq['iterations'], 120)
        self.assertEqual(eq['win_count']+eq['tie_count']+eq['loss_count'], 120)
        self.assertAlmostEqual(eq['terminal_call_ev_model']['call_ev_incremental'],
                               eq['equity']*120-20)
        self.assertTrue(eq['equity_ci95_sampling_only'][0] <= eq['equity'] <=
                        eq['equity_ci95_sampling_only'][1])
        self.assertFalse(result['action_observed_or_graded'])
        self.assertEqual(batch.verify_results(self.output, self.input)['verified'], 1)

    def test_reproducible_output_bytes(self):
        self.run_batch()
        first = (self.output / 'H001.equity.json').read_bytes()
        other = self.root / 'other'
        batch.run(self.input, other)
        self.assertEqual(first, (other / 'H001.equity.json').read_bytes())
        self.assertEqual((self.output / 'manifest.json').read_bytes(),
                         (other / 'manifest.json').read_bytes())

    def test_blocked_only_no_math(self):
        d = fixture()
        d['entries'][0]['eligible_for_offline_monte_carlo'] = False
        d['entries'][0]['equity_input'] = None
        d['entries'][0]['blocked_reasons'] = ['review_incomplete']
        d['eligible_count'] = 0
        d['blocked_count'] = 2
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'no eligible'):
            self.run_batch()
        self.assertFalse(self.output.exists())

    def test_count_tamper_rejected(self):
        d = fixture()
        d['eligible_count'] = 2
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'counts mismatch'):
            self.run_batch()
        self.assertFalse(self.output.exists())

    def test_duplicate_hand_rejected(self):
        d = fixture()
        d['entries'][1]['hand_id'] = 'H001'
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.run_batch()

    def test_more_than_four_tables_rejected(self):
        d = fixture()
        for i in range(3, 6):
            r = copy.deepcopy(d['entries'][1])
            r['hand_id'] = f'H00{i}'
            r['table_id'] = f'T{i}'
            d['entries'].append(r)
        d['blocked_count'] += 3
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'four tables'):
            self.run_batch()

    def test_safety_limit_per_hand(self):
        d = fixture()
        d['entries'][0]['equity_input']['iterations'] = 5001
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'per-hand'):
            self.run_batch()
        self.assertFalse(self.output.exists())

    def test_invalid_cards_fail_without_output(self):
        d = fixture()
        d['entries'][0]['equity_input']['board_cards'][0] = 'As'
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.run_batch()
        self.assertFalse(self.output.exists())

    def test_unconfirmed_input_rejected(self):
        d = fixture()
        d['entries'][0]['equity_input']['manual_review_confirmed'] = False
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'reviewed input'):
            self.run_batch()

    def test_provenance_flags_cannot_be_upgraded(self):
        d = fixture()
        d['ocr_semantics_verified'] = True
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.run_batch()

    def test_unexpected_claims_rejected(self):
        d = fixture()
        d['action_correct'] = True
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'unexpected queue fields'):
            self.run_batch()

    def test_no_overwrite(self):
        self.run_batch()
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'new directory'):
            self.run_batch()
        self.assertEqual((self.output / 'manifest.json').read_bytes(), before)

    def test_symlink_queue_rejected(self):
        link = self.root / 'link.json'
        link.symlink_to(self.input)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            batch.run(link, self.output)

    def test_tampered_result_hash_rejected(self):
        self.run_batch()
        (self.output / 'H001.equity.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            batch.verify_results(self.output)

    def test_tampered_queue_hash_rejected(self):
        self.run_batch()
        self.input.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'source queue digest mismatch'):
            batch.verify_results(self.output, self.input)

    def test_unexpected_file_rejected(self):
        self.run_batch()
        (self.output / 'extra.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'file set'):
            batch.verify_results(self.output)

    def test_result_symlink_rejected(self):
        self.run_batch()
        result = self.output / 'H001.equity.json'
        other = self.root / 'other.json'
        result.rename(other)
        result.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            batch.verify_results(self.output)

    def test_duplicate_json_keys_rejected(self):
        self.input.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            self.run_batch()

    def test_nonfinite_json_rejected(self):
        self.input.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.run_batch()

    def test_plo6_weighted_range(self):
        d = fixture()
        inp = d['entries'][0]['equity_input']
        inp['variant'] = 'PLO6'
        inp['hero_cards'].append('9s')
        inp['opponent_model'] = {'kind': 'weighted_combos', 'combos': [
            {'cards': ['5c','6c','7c','8c','9c','Th'], 'weight': 1}]}
        inp['iterations'] = 30
        self.write(d)
        self.run_batch()
        eq = json.loads((self.output / 'H001.equity.json').read_text())['equity_result']
        self.assertEqual(eq['variant'], 'PLO6')
        self.assertEqual(eq['range_eligible_combos'], 1)
        self.assertEqual(eq['win_count'] + eq['tie_count'] + eq['loss_count'], 30)

    def test_engine_failure_does_not_create_directory(self):
        with patch.object(batch.monte_carlo, 'analyze', side_effect=RuntimeError('fail')):
            with self.assertRaisesRegex(RuntimeError, 'fail'):
                self.run_batch()
        self.assertFalse(self.output.exists())

    def test_four_table_batch_runs_and_preserves_table_identity(self):
        d = fixture()
        original = d['entries'][0]
        d['entries'] = []
        for i in range(1, 5):
            r = copy.deepcopy(original)
            r['hand_id'] = f'H00{i}'
            r['table_id'] = f'T{i}'
            r['equity_input']['iterations'] = 10
            r['equity_input']['seed'] = 40 + i
            d['entries'].append(r)
        d['eligible_count'], d['blocked_count'] = 4, 0
        self.write(d)
        manifest = self.run_batch()
        self.assertEqual(manifest['eligible_executed'], 4)
        self.assertEqual(manifest['total_iterations'], 40)
        self.assertEqual({r['table_id'] for r in manifest['entries']},
                         {'T1', 'T2', 'T3', 'T4'})
        self.assertEqual(batch.verify_results(self.output, self.input)['verified'], 4)

    def test_total_iteration_limit_blocks_before_output(self):
        d = fixture()
        original = d['entries'][0]
        d['entries'] = []
        for i in range(1, 6):
            r = copy.deepcopy(original)
            r['hand_id'] = f'H00{i}'
            r['equity_input']['iterations'] = 5000
            d['entries'].append(r)
        d['eligible_count'], d['blocked_count'] = 5, 0
        self.write(d)
        with self.assertRaisesRegex(ValueError, 'batch iteration'):
            self.run_batch()
        self.assertFalse(self.output.exists())

    def test_cli_verify(self):
        self.assertEqual(batch.main([str(self.input), str(self.output)]), 0)
        self.assertEqual(batch.main(['--verify', str(self.output), str(self.input)]), 0)


if __name__ == '__main__':
    unittest.main()
