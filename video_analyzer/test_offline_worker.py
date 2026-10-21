import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_jobs import OfflineJobStore
from offline_worker import process_next

class OfflineWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'recording.mp4'
        self.source.write_bytes(b'example video data')
        self.store = OfflineJobStore(self.root / 'queue.sqlite')
        self.metadata = {'size_bytes': self.source.stat().st_size,
                         'duration_seconds': 3., 'width': 320, 'height': 240}
        self.validator = patch('offline_jobs.validate_recording', return_value=self.metadata)
        self.validator.start()
        self.addCleanup(self.validator.stop)

    def test_empty_queue(self):
        self.assertIsNone(process_next(self.store, self.root / 'out'))

    def test_valid_job_requires_review(self):
        self.store.enqueue(self.source)
        with patch('offline_worker.export_evidence', return_value={'requires_manual_review': True}) as sampler:
            job = process_next(self.store, self.root / 'out')
        self.assertEqual(job['state'], 'review_required')
        self.assertEqual(job['attempts'], 1)
        self.assertTrue(job['result_path'].endswith('manifest.json'))
        self.assertEqual(sampler.call_count, 1)

    def test_mutated_file_rejected_without_sampling(self):
        self.store.enqueue(self.source)
        self.source.write_bytes(b'altered')
        with patch('offline_worker.export_evidence') as sampler:
            job = process_next(self.store, self.root / 'out')
        self.assertEqual(job['state'], 'failed')
        self.assertIn('changed', job['error'])
        sampler.assert_not_called()

    def test_sampler_failure_is_persisted(self):
        self.store.enqueue(self.source)
        with patch('offline_worker.export_evidence', side_effect=RuntimeError('synthetic failure')):
            job = process_next(self.store, self.root / 'out')
        self.assertEqual(job['state'], 'failed')
        self.assertIn('synthetic failure', job['error'])
        self.assertTrue(self.source.exists())

    def test_unreviewed_result_cannot_be_silently_approved(self):
        self.store.enqueue(self.source)
        with patch('offline_worker.export_evidence', return_value={'requires_manual_review': False}):
            job = process_next(self.store, self.root / 'out')
        self.assertEqual(job['state'], 'failed')

if __name__ == '__main__':
    unittest.main()
