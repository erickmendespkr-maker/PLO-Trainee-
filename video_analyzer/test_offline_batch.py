import unittest
from unittest.mock import patch
from offline_batch import process_batch

class BatchTests(unittest.TestCase):
    def test_empty_queue(self):
        with patch('offline_batch.process_next', return_value=None) as worker:
            result = process_batch(object(), 'out')
        self.assertEqual(result['processed'], 0)
        worker.assert_called_once()

    def test_respects_limit(self):
        job = {'job_id': 'synthetic', 'state': 'review_required', 'error': None}
        with patch('offline_batch.process_next', return_value=job) as worker:
            result = process_batch(object(), 'out', max_jobs=3)
        self.assertEqual(result['processed'], 3)
        self.assertEqual(result['review_required'], 3)
        self.assertEqual(worker.call_count, 3)

    def test_failure_does_not_block_following_jobs(self):
        jobs = [{'job_id': 'a', 'state': 'failed', 'error': 'synthetic'},
                {'job_id': 'b', 'state': 'review_required', 'error': None}, None]
        with patch('offline_batch.process_next', side_effect=jobs):
            result = process_batch(object(), 'out')
        self.assertEqual((result['processed'], result['failed'], result['review_required']), (2, 1, 1))

    def test_rejects_invalid_limit(self):
        for value in [0, 101, True, 2.5, '10']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                process_batch(object(), 'out', max_jobs=value)

if __name__ == '__main__':
    unittest.main()
