import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from local_ingest import ingest_local
from offline_jobs import OfflineJobStore

class LocalIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'example.mp4'
        self.source.write_bytes(b'synthetic content')
        self.storage = self.root / 'uploads'
        self.database = self.root / 'jobs.db'
        self.patcher = patch('local_ingest.validate_recording', return_value={'size_bytes': self.source.stat().st_size})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.queue_patcher = patch('offline_jobs.validate_recording', return_value={'size_bytes': self.source.stat().st_size})
        self.queue_patcher.start()
        self.addCleanup(self.queue_patcher.stop)

    def test_ingests_and_queues_private_copy(self):
        job = ingest_local(self.source, self.storage, self.database)
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(Path(job['source_path']).read_bytes(), self.source.read_bytes())
        self.assertNotEqual(Path(job['source_path']), self.source)
        self.assertEqual(OfflineJobStore(self.database).get(job['job_id'])['state'], 'queued')

    def test_rejects_source_already_in_storage(self):
        self.storage.mkdir()
        source = self.storage / 'example.mp4'
        source.write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):
            ingest_local(source, self.storage, self.database)

    def test_queue_failure_removes_copied_file(self):
        with patch('local_ingest.OfflineJobStore', side_effect=RuntimeError('db unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'db unavailable'):
                ingest_local(self.source, self.storage, self.database)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_copy_size_mismatch_rejected(self):
        with patch('local_ingest.shutil.copyfileobj', side_effect=lambda src, dst, length: dst.write(b'x')):
            with self.assertRaisesRegex(ValueError, 'changed'):
                ingest_local(self.source, self.storage, self.database)
        self.assertEqual(list(self.storage.iterdir()), [])

if __name__ == '__main__':
    unittest.main()
