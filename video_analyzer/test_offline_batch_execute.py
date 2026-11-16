import json
import tempfile
import unittest
from pathlib import Path
from offline_batch_execute import execute_review_batch


def record(start, end, table=1):
    return {'start_pts': start, 'end_pts': end, 'table_id': table,
            **{k: False for k in ('table_verified', 'hand_verified',
               'hero_cards_verified', 'board_verified', 'action_verified', 'amounts_verified')}}


class BatchExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'input.mp4'
        self.src.write_bytes(b'synthetic-input')
        self.dst = self.root / 'review_table1_0001.mp4'
        self.plan = [{'destination': str(self.dst), 'record': record(0, 2),
                      'status': 'PLANNED_ONLY', 'human_review_required': True}]

    def writer(self, src, dst, rec):
        dst.write_bytes(b'clip')
        dst.with_suffix('.json').write_text(json.dumps({'reviewed': False}))
        return {'clip_sha256': 'synthetic'}

    def test_success(self):
        out = execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer)
        self.assertEqual(out['status'], 'EXPORTED_UNREVIEWED')
        self.assertTrue(out['human_review_required'])
        self.assertFalse(self.dst.with_suffix('.mp4.lock').exists())

    def test_preexisting_output(self):
        self.dst.write_bytes(b'old')
        with self.assertRaises(FileExistsError):
            execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer)
        self.assertEqual(self.dst.read_bytes(), b'old')

    def test_existing_lock(self):
        lock = self.dst.with_suffix('.mp4.lock')
        lock.write_text('other worker')
        out = execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer)
        self.assertEqual(out['status'], 'PARTIAL_OR_FAILED')
        self.assertEqual(lock.read_text(), 'other worker')

    def test_failed_export(self):
        def fail(*args):
            raise RuntimeError('synthetic ffmpeg failure')
        out = execute_review_batch(self.src, self.plan, 4, self.root, exporter=fail)
        self.assertEqual(out['results'][0]['error_type'], 'RuntimeError')
        self.assertFalse(self.dst.with_suffix('.mp4.lock').exists())

    def test_missing_sidecar(self):
        def incomplete(src, dst, rec):
            dst.write_bytes(b'incomplete')
            return {}
        out = execute_review_batch(self.src, self.plan, 4, self.root, exporter=incomplete)
        self.assertEqual(out['status'], 'PARTIAL_OR_FAILED')

    def test_invalid_evidence(self):
        self.plan[0]['record']['hand_verified'] = True
        with self.assertRaises(ValueError):
            execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer)

    def test_invalid_source(self):
        self.src.unlink()
        with self.assertRaises(ValueError):
            execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer)

    def test_empty_prepared_batch_never_reports_success(self):
        from unittest.mock import patch
        with patch('offline_batch_execute.prepare_batch',
                   return_value={'clips': [], 'total_seconds': 0}):
            out = execute_review_batch(self.src, [], 4, self.root, exporter=self.writer)
        self.assertEqual(out['status'], 'PARTIAL_OR_FAILED')
        self.assertEqual(out['attempted_count'], 0)

    def test_invalid_stop_flag(self):
        with self.assertRaises(ValueError):
            execute_review_batch(self.src, self.plan, 4, self.root, exporter=self.writer, stop_on_error=1)


if __name__ == '__main__':
    unittest.main()
