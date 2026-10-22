import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_jobs import OfflineJobStore
from job_status import status_report

class JobStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'jobs.sqlite'
        self.source = Path(self.temp.name) / 'recording.mp4'
        self.source.write_bytes(b'fake test data')
        self.store = OfflineJobStore(self.database)

    def test_empty(self):
        self.assertEqual(status_report(self.database), {'counts': {}, 'jobs': []})

    def test_status_redacts_private_path_and_hash(self):
        with patch('offline_jobs.validate_recording', return_value={'size_bytes': self.source.stat().st_size}):
            job = self.store.enqueue(self.source)
        report = status_report(self.database)
        self.assertEqual(report['counts'], {'queued': 1})
        self.assertEqual(report['jobs'][0]['job_id'], job['job_id'])
        self.assertNotIn('source_path', report['jobs'][0])
        self.assertNotIn('source_sha256', report['jobs'][0])
        self.assertEqual(status_report(self.database, job_id=job['job_id'])['job']['state'], 'queued')

    def test_missing_id(self):
        self.assertIsNone(status_report(self.database, job_id='0'*32)['job'])

    def test_invalid_arguments(self):
        for limit in (0, 501, True, '10'):
            with self.assertRaises(ValueError):
                status_report(self.database, limit=limit)
        with self.assertRaises(ValueError):
            status_report(self.database, job_id='../etc/passwd')

if __name__ == '__main__':
    unittest.main()
