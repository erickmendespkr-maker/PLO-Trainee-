import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import strategic_store as s
import strategic_backup as b


class BackupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / 'source.sqlite'
        self.target = self.root / 'backup.sqlite'
        self.db = s.connect(self.source)
        self.addCleanup(self.db.close)
        self.key = s.add_source(self.db, 'fixture', 'test only', 'local')
        self.context = {'position': 'BTN'}
        s.add_record(self.db, self.key, 5, self.context, {'fold': 1}, synthetic=True)
        s.record_permission_review(self.db, self.key, status='restricted', local_use=False,
            redistribution=False, reviewer='test', reviewed_on='2026-11-25',
            evidence_ref='fixture', evidence_sha256='a'*64, source_version='v1', scope='test')

    def test_roundtrip(self):
        report = b.backup(self.source, self.target)
        restored = self.root / 'restored.sqlite'
        result = b.restore(self.target, restored, expected_sha256=report['sha256'])
        self.assertEqual(report['counts'], result['counts'])
        self.assertEqual(report['counts'], dict(sources=1, scenarios=1, records=1, source_permission_reviews=1, import_batches=0, import_batch_records=0))
        with b.closing(s.connect(restored)) as db:
            self.assertEqual(s.lookup(db, 5, self.context, synthetic=True), [(self.key, {'fold': 1})])
            self.assertEqual(s.lookup(db, 5, self.context), [])
            self.assertEqual(s.source_permission(db, self.key)['status'], 'restricted')

    def test_existing_destination(self):
        self.target.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            b.backup(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'keep')
        with self.assertRaises(FileExistsError):
            b.backup(self.source, self.source)

    def test_missing_source(self):
        missing = self.root / 'missing.sqlite'
        with self.assertRaises(FileNotFoundError):
            b.backup(missing, self.target)
        self.assertFalse(missing.exists())
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.strategic-*')))

    def test_wrong_digest(self):
        b.backup(self.source, self.target)
        restored = self.root / 'restored.sqlite'
        with self.assertRaises(ValueError):
            b.restore(self.target, restored, expected_sha256='0'*64)
        self.assertFalse(restored.exists())

    def test_invalid_schema(self):
        self.db.execute('DROP INDEX records_lookup')
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'schema'):
            b.backup(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_invalid_payload(self):
        self.db.execute("UPDATE records SET payload='{}'")
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'strategy record'):
            b.backup(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_wrong_version(self):
        self.db.execute('PRAGMA user_version=2')
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'version'):
            b.backup(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_wal_committed(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        s.add_record(self.db, self.key, 6, self.context, {'call': 1}, synthetic=True)
        self.db.execute("UPDATE records SET payload='{}'")
        try:
            result = b.backup(self.source, self.target)
            self.assertEqual(result['counts']['records'], 2)
        finally:
            self.db.rollback()

    def test_publication_race(self):
        def race(src, dst):
            Path(dst).write_bytes(b'concurrent file')
            raise FileExistsError(dst)
        with patch.object(os, 'link', side_effect=race):
            with self.assertRaises(FileExistsError):
                b.backup(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'concurrent file')
        self.assertFalse(list(self.root.glob('.strategic-*')))

    def test_invalid_database_bytes(self):
        bad = self.root / 'bad.sqlite'
        bad.write_bytes(b'not SQLite')
        with self.assertRaises(sqlite3.DatabaseError):
            b.backup(bad, self.target)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
