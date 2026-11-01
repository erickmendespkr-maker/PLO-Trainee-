"""Offline synthetic throughput/contract regression tests for the existing MC engine."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_mc_four_table_benchmark as b
import offline_omaha_equity_mc as mc


class FourTableBenchmarkTests(unittest.TestCase):
    def test_four_tables_both_variants(self):
        r = b.benchmark(100)
        self.assertEqual(len(r['tables']), 4)
        self.assertEqual([t['variant'] for t in r['tables']], ['PLO5','PLO6','PLO5','PLO6'])
        self.assertEqual(r['total_trials'], 400)
        self.assertEqual(r['status'], b.STATUS)

    def test_engine_hash_matches_local_file(self):
        self.assertEqual(b.benchmark(100)['engine_git_blob_sha'], b.git_blob_sha(Path(mc.__file__).read_bytes()))

    def test_reproducible_except_timing(self):
        a, c = b.benchmark(100), b.benchmark(100)
        for row in a['tables']:
            row.pop('elapsed_seconds')
        for row in c['tables']:
            row.pop('elapsed_seconds')
        a.pop('total_elapsed_seconds')
        c.pop('total_elapsed_seconds')
        self.assertEqual(a, c)

    def test_every_row_counts_and_confidence(self):
        for t in b.benchmark(100)['tables']:
            self.assertEqual(t['wins'] + t['ties'] + t['losses'], 100)
            lo, hi = t['equity_95pct_hoeffding_interval']
            self.assertLessEqual(lo, t['equity_estimate'])
            self.assertLessEqual(t['equity_estimate'], hi)
            self.assertGreaterEqual(t['elapsed_seconds'], 0)

    def test_scenarios_are_valid(self):
        for i in range(4):
            self.assertEqual(len(mc.validate_scenario(b.scenario(i,100))['eligible_hands']), 2)

    def test_invalid_table_and_sample_rejected(self):
        for i in (-1, 4, True, 1.5):
            with self.subTest(table=i), self.assertRaises(ValueError): b.scenario(i, 100)
        for n in (99, 2001, True, 100.0):
            with self.subTest(samples=n), self.assertRaises(ValueError): b.scenario(0, n)

    def test_invalid_clock_rejected(self):
        with patch.object(b.mc, 'estimate', wraps=mc.estimate):
            with self.assertRaises(ValueError): b.benchmark(100, clock=lambda: float('nan'))

    def test_report_file_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'benchmark.json'
            b.write_new({'status': b.STATUS}, target)
            self.assertEqual(json.loads(target.read_text())['status'], b.STATUS)
            with self.assertRaises(ValueError): b.write_new({}, target)

    def test_report_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'benchmark.json'
            other = Path(d) / 'other.json'
            other.write_text('unchanged')
            target.symlink_to(other)
            with self.assertRaises(ValueError): b.write_new({}, target)
            self.assertEqual(other.read_text(), 'unchanged')

    def test_output_extension_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): b.write_new({}, Path(d) / 'bad.txt')


if __name__ == '__main__':
    unittest.main()
