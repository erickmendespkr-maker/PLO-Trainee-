"""Synthetic regression tests for >100 reviewed clips and bounded math batches."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_session_batch_planner as batch
from test_offline_reviewed_hand_math_queue import fixture


class BatchPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan, self.ann = fixture()
        self.plan_path = self.root/'plan.json'
        self.ann_path = self.root/'annotations.json'
        self.dest = self.root/'batches'

    def write(self):
        self.plan_path.write_bytes(batch.encode(self.plan))
        self.ann['source_plan_sha256'] = batch.q.digest(self.plan_path)
        self.ann_path.write_bytes(batch.encode(self.ann))

    def add_clips(self, total):
        self.plan['clips'] = []
        for n in range(total):
            table = n % 4
            t = (n//4) * 3.5
            self.plan['clips'].append({'hand_id': f'H{n:04d}', 'table_id': f'T{table+1}',
                'start_seconds': t, 'end_seconds': t+3,
                'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        self.ann['hands'] = []

    def test_300_clips_four_tables_no_simulations(self):
        self.add_clips(300)
        self.write()
        result = batch.process(self.plan_path, self.ann_path, self.dest)
        self.assertEqual((result['batches'], result['clips'], result['eligible']), (3, 300, 0))
        self.assertTrue(batch.process(self.plan_path, self.ann_path, self.dest, True)['verified'])
        self.assertEqual(json.loads((self.dest/'manifest.json').read_text())['total_clips'], 300)

    def test_4000_clips_boundary(self):
        self.add_clips(4000)
        self.write()
        result = batch.process(self.plan_path, self.ann_path, self.dest)
        self.assertEqual((result['batches'], result['clips']), (40, 4000))

    def test_4001_rejected(self):
        self.add_clips(4001)
        self.write()
        with self.assertRaisesRegex(ValueError, 'invalid long-session'):
            batch.process(self.plan_path, self.ann_path, self.dest)
        self.assertFalse(self.dest.exists())

    def test_eligible_limit_splits_before_100(self):
        self.add_clips(50)
        for c in self.plan['clips']:
            h = copy.deepcopy(fixture()[1]['hands'][0])
            h['hand_id'], h['table_id'] = c['hand_id'], c['table_id']
            h['card_evidence'] = [{**x, 'pts_seconds': c['start_seconds']+1} for x in h['card_evidence']]
            self.ann['hands'].append(h)
        self.write()
        result = batch.process(self.plan_path, self.ann_path, self.dest)
        self.assertEqual((result['batches'], result['eligible']), (3, 50))
        self.assertTrue(batch.process(self.plan_path, self.ann_path, self.dest, True)['verified'])

    def test_iteration_budget_splits(self):
        self.add_clips(10)
        for c in self.plan['clips']:
            h = copy.deepcopy(fixture()[1]['hands'][0])
            h['hand_id'], h['table_id'], h['iterations'] = c['hand_id'], c['table_id'], 50000
            h['card_evidence'] = [{**x, 'pts_seconds': c['start_seconds']+1} for x in h['card_evidence']]
            self.ann['hands'].append(h)
        self.write()
        self.assertEqual(batch.process(self.plan_path, self.ann_path, self.dest)['batches'], 3)

    def test_cross_table_overlap_allowed(self):
        self.write()
        self.assertEqual(batch.process(self.plan_path, self.ann_path, self.dest)['clips'], 2)

    def test_same_table_overlap_rejected(self):
        self.plan['clips'][1]['table_id'] = 'T1'
        self.write()
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            batch.process(self.plan_path, self.ann_path, self.dest)

    def test_duplicate_hand_rejected(self):
        self.plan['clips'][1]['hand_id'] = 'H001'
        self.write()
        with self.assertRaisesRegex(ValueError, 'duplicate hand'):
            batch.process(self.plan_path, self.ann_path, self.dest)

    def test_wrong_annotation_binding_rejected(self):
        self.write()
        self.ann['source_plan_sha256'] = 'f'*64
        self.ann_path.write_bytes(batch.encode(self.ann))
        with self.assertRaisesRegex(ValueError, 'unbound'):
            batch.process(self.plan_path, self.ann_path, self.dest)

    def test_tampered_batch_rejected(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        f = self.dest/'batch-0001/queue.json'
        f.write_text(f.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'differs'):
            batch.process(self.plan_path, self.ann_path, self.dest, True)

    def test_extra_file_rejected(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        (self.dest/'unexpected.txt').write_text('bad')
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            batch.process(self.plan_path, self.ann_path, self.dest, True)

    def test_symlink_rejected(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        target = self.dest/'batch-0001/plan.json'
        target.unlink()
        try:
            target.symlink_to(self.plan_path)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'batch input differs'):
            batch.process(self.plan_path, self.ann_path, self.dest, True)

    def test_no_overwrite(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            batch.process(self.plan_path, self.ann_path, self.dest)

    def test_changed_source_rejected(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        self.plan_path.write_text(self.plan_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'unbound'):
            batch.process(self.plan_path, self.ann_path, self.dest, True)

    def test_timestamp_above_60_minutes_rejected(self):
        self.plan['clips'][0]['start_seconds'] = 3595
        self.plan['clips'][0]['end_seconds'] = 3605
        self.write()
        with self.assertRaisesRegex(ValueError, '60 minutes'):
            batch.process(self.plan_path, self.ann_path, self.dest)

    def test_first_batch_can_run_real_monte_carlo_synthetic(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        folder = self.dest/'batch-0001'
        result = batch.runner.run(folder/'plan.json', folder/'annotations.json',
                                  folder/'queue.json', self.root/'math')
        self.assertEqual((result['eligible_analyzed_count'], result['blocked_count']), (1, 1))
        self.assertEqual(batch.runner.verify_results(folder/'plan.json',
                         folder/'annotations.json', folder/'queue.json',
                         self.root/'math')['verified'], 1)

    def test_deterministic_bytes(self):
        self.add_clips(201)
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        second = self.root/'again'
        batch.process(self.plan_path, self.ann_path, second)
        for left in self.dest.rglob('*'):
            if left.is_file():
                self.assertEqual(left.read_bytes(), (second/left.relative_to(self.dest)).read_bytes())

    def test_no_main_branch_or_live_features(self):
        self.write()
        batch.process(self.plan_path, self.ann_path, self.dest)
        self.assertFalse(json.loads((self.dest/'manifest.json').read_text())['monte_carlo_executed'])


if __name__ == '__main__':
    unittest.main()
