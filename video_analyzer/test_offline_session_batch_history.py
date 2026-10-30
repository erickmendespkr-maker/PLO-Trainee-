"""Synthetic resumable cross-batch execution tests; no real video or poker access."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_session_batch_history as history
import offline_session_batch_planner as planner
from test_offline_reviewed_hand_math_queue import fixture


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan, self.ann = fixture()
        self.plan['clips'] = []
        self.ann['hands'] = []
        for n in range(205):
            table = n % 4
            t = (n//4)*4
            self.plan['clips'].append({'hand_id': f'H{n:04d}',
                'table_id': f'T{table+1}', 'start_seconds': t,
                'end_seconds': t+3, 'review_basis':
                'human_declared_boundaries_not_automatic_detection'})
        h = copy.deepcopy(fixture()[1]['hands'][0])
        h['hand_id'], h['table_id'] = 'H0000', 'T1'
        h['card_evidence'] = [{**x, 'pts_seconds': 1} for x in h['card_evidence']]
        self.ann['hands'] = [h]
        self.plan_path = self.root/'plan.json'
        self.ann_path = self.root/'annotations.json'
        self.batches = self.root/'batches'
        self.results = self.root/'results'
        self.plan_path.write_bytes(planner.encode(self.plan))
        self.ann['source_plan_sha256'] = planner.q.digest(self.plan_path)
        self.ann_path.write_bytes(planner.encode(self.ann))
        planner.process(self.plan_path, self.ann_path, self.batches)

    def run_history(self, **kw):
        return history.process(self.plan_path, self.ann_path, self.batches, self.results, **kw)

    def test_partial_resume_complete_and_verify(self):
        first = self.run_history()
        self.assertEqual((first['completed_batches'], first['total_batches']), (1, 3))
        self.assertEqual((first['eligible_analyzed'], first['blocked']), (1, 99))
        self.assertFalse(first['complete'])
        second = self.run_history(max_new=1)
        self.assertEqual(second['completed_batches'], 2)
        third = self.run_history(max_new=10)
        self.assertTrue(third['complete'])
        self.assertEqual((third['total_hands_reviewed'], third['blocked']), (205, 204))
        self.assertEqual(third['total_iterations'], 120)
        self.assertEqual(len(third['hands']), 205)
        self.assertEqual(self.run_history(verify=True), third)
        self.assertEqual(self.run_history(max_new=1), third)

    def test_crash_after_batch_before_history_update(self):
        self.run_history()
        src = self.batches/'batch-0002'
        history.runner.run(src/'plan.json', src/'annotations.json', src/'queue.json',
                           self.results/'batch-0002')
        state = self.run_history(max_new=0)
        self.assertEqual(state['completed_batches'], 2)
        self.assertEqual(self.run_history(verify=True), state)

    def test_reject_tampered_history(self):
        self.run_history()
        path = self.results/history.HISTORY_NAME
        value = json.loads(path.read_text())
        value['hands'][0]['status'] = 'fake'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'previous history differs'):
            self.run_history()

    def test_reject_tampered_math_result(self):
        self.run_history()
        f = self.results/'batch-0001/hands/H0000.json'
        f.write_text(f.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.run_history(max_new=0)

    def test_reject_tampered_plan(self):
        self.run_history()
        self.plan_path.write_text(self.plan_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'unbound'):
            self.run_history(max_new=0)

    def test_reject_unknown_results_file(self):
        self.run_history()
        (self.results/'rogue.txt').write_text('bad')
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            self.run_history()

    def test_reject_non_prefix_batch(self):
        self.run_history(max_new=0)
        src = self.batches/'batch-0002'
        history.runner.run(src/'plan.json', src/'annotations.json', src/'queue.json',
                           self.results/'batch-0002')
        with self.assertRaisesRegex(ValueError, 'non-prefix'):
            self.run_history()

    def test_reject_result_symlink(self):
        self.run_history()
        f = self.results/'batch-0001'
        link = self.results/'rogue'
        try:
            link.symlink_to(f, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.run_history()

    def test_reject_history_symlink(self):
        self.run_history()
        path = self.results/history.HISTORY_NAME
        backup = self.root/'backup.json'
        path.rename(backup)
        try:
            path.symlink_to(backup)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.run_history()

    def test_reject_changed_math_manifest(self):
        self.run_history()
        f = self.results/'batch-0001/manifest.json'
        m = json.loads(f.read_text())
        m['total_iterations'] = 999
        f.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'totals mismatch'):
            self.run_history()

    def test_bounded_max_new(self):
        with self.assertRaisesRegex(ValueError, 'max-new'):
            self.run_history(max_new=101)
        self.assertFalse(self.results.exists())

    def test_verify_missing_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            self.run_history(verify=True)

    def test_zero_budget_and_empty_history(self):
        state = self.run_history(max_new=0)
        self.assertEqual(state['completed_batches'], 0)
        self.assertEqual(state['hands'], [])
        self.assertEqual(self.run_history(verify=True), state)

    def test_source_not_overwritten(self):
        original = (self.batches/'manifest.json').read_bytes()
        self.run_history(max_new=3)
        self.assertEqual((self.batches/'manifest.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
