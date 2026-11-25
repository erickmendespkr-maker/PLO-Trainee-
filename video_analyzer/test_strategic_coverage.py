import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import strategic_store as s
import strategic_import as imp
import strategic_coverage as c
import strategic_backup as b
from test_strategic_normalize import scenario, actions


class CoverageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'store.db'
        self.db = s.connect(self.path)
        self.addCleanup(self.db.close)
        self.source = s.add_source(self.db, 'fixture', 'test only', 'local')
        self.row = dict(variant=5, scenario=scenario(), actions=actions())

    def load(self, rows, source=None, name='data.json'):
        path = self.root / name
        path.write_text(json.dumps(dict(format=imp.FORMAT_V2, records=rows)))
        return imp.import_fixture(self.db, path, source_id=source or self.source, synthetic=True)

    def test_replay_and_occurrences(self):
        first = self.load([self.row, self.row])
        second = self.load([self.row, self.row])
        self.assertEqual(first['batch_id'], second['batch_id'])
        self.assertFalse(first['replayed'])
        self.assertTrue(second['replayed'])
        self.assertEqual(second['inserted'], 0)
        self.assertEqual(self.db.execute('SELECT row_count,inserted FROM import_batches').fetchall(), [(2,1)])
        self.assertEqual(self.db.execute('SELECT occurrences FROM import_batch_records').fetchall(), [(2,)])

    def test_separate_sources(self):
        other = s.add_source(self.db, 'other', 'test only', 'local')
        self.assertNotEqual(self.load([self.row])['batch_id'], self.load([self.row],other)['batch_id'])
        report = c.coverage(self.db, synthetic=True)
        self.assertEqual((report['records'], report['scenarios'], report['batches']), (2,1,2))
        self.assertEqual(report['divergences'], [])

    def test_divergence_retained(self):
        self.load([self.row])
        self.load([dict(self.row, actions=[dict(action='fold', size=0, frequency=1, ev=0)])])
        report = c.coverage(self.db, synthetic=True)
        self.assertEqual(report['records'], 2)
        self.assertEqual(len(report['divergences']), 1)
        self.assertEqual(len(report['divergences'][0]['record_ids']), 2)
        self.assertEqual(len(s.lookup(self.db,5,scenario(),synthetic=True)),2)

    def test_dimensions_and_legacy(self):
        self.load([self.row, dict(self.row, variant=6, scenario=scenario(hero=scenario()['hero']+['9s']))])
        s.add_record(self.db,self.source,5,{'position':'BTN'},{'fold':1},synthetic=True)
        report = c.coverage(self.db, synthetic=True)
        self.assertEqual(report['normalized_records'],2)
        self.assertEqual({(g['variant'],g['street']) for g in report['groups']}, {(5,'flop'),(6,'flop'),(5,'UNKNOWN')})
        self.assertEqual(c.coverage(self.db)['records'],0)
        self.assertEqual(c.coverage(self.db)['batches'],0)

    def test_transaction_failure(self):
        with patch.object(c,'persist_batch',side_effect=sqlite3.IntegrityError('fixture failure')), self.assertRaises(sqlite3.IntegrityError):
            self.load([self.row])
        self.assertEqual(c.coverage(self.db,synthetic=True)['records'],0)
        self.assertEqual(c.coverage(self.db,synthetic=True)['batches'],0)

    def test_backup_and_audit(self):
        self.load([self.row])
        report = b.backup(self.path,self.root/'copy.db')
        self.assertEqual(report['counts']['import_batches'],1)
        self.db.execute('UPDATE import_batch_records SET occurrences=2')
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'batch'):
            b.backup(self.path,self.root/'invalid.db')

    def test_v3_migration(self):
        old = self.root/'old.db'
        with b.closing(sqlite3.connect(old)) as db:
            db.executescript(s.SCHEMA)
            for statement in s.PERMISSION_SCHEMA:
                db.execute(statement)
            db.execute('PRAGMA user_version=3')
            db.commit()
            source = s.add_source(db,'legacy','test only','local')
            key = s.add_record(db,source,5,{'position':'BTN'},{'fold':1},synthetic=True)
        with b.closing(s.connect(old)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT id FROM records').fetchone()[0],key)
            self.assertEqual(c.coverage(db,synthetic=True)['batches'],0)

    def test_v3_migration_rollback(self):
        old = self.root/'broken.db'
        with b.closing(sqlite3.connect(old)) as db:
            db.executescript(s.SCHEMA)
            for statement in s.PERMISSION_SCHEMA:
                db.execute(statement)
            db.execute('PRAGMA user_version=3')
            db.execute('CREATE TABLE batch_record_lookup(x INTEGER)')
            db.commit()
            with self.assertRaises(sqlite3.OperationalError):
                s.connect(old)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='import_batches'").fetchone())


if __name__ == '__main__':
    unittest.main()
