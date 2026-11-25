import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import strategic_import as imp
import strategic_store as s


class ImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = s.connect(self.root / 'store.sqlite')
        self.addCleanup(self.db.close)
        self.source = s.add_source(self.db, 'fixture', 'test only', 'local')
        self.row = dict(variant=5, scenario={'position': 'BTN'}, actions={'fold': .2, 'raise': .8})

    def file(self, suffix, rows):
        path = self.root / ('input.' + suffix)
        if suffix == 'json':
            path.write_text(json.dumps(dict(format=imp.FORMAT, records=rows)), encoding='utf-8')
        else:
            with path.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle, delimiter=',' if suffix == 'csv' else '\t')
                writer.writerow(imp.FIELDS)
                for row in rows:
                    writer.writerow([row['variant'], json.dumps(row['scenario']), json.dumps(row['actions'])])
        return path

    def load(self, path, **changes):
        return imp.import_fixture(self.db, path, **dict(dict(source_id=self.source, synthetic=True), **changes))

    def count(self):
        return self.db.execute('SELECT count(*) FROM records').fetchone()[0]

    def test_three_formats(self):
        for suffix in ('csv', 'json', 'txt'):
            with self.subTest(suffix=suffix):
                path = self.file(suffix, [self.row])
                report = self.load(path)
                self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(report['inserted'], int(suffix == 'csv'))
                self.assertEqual(report['duplicates'], int(suffix != 'csv'))
        self.assertEqual(s.lookup(self.db, 5, self.row['scenario'], synthetic=True), [(self.source, self.row['actions'])])
        self.assertEqual(s.lookup(self.db, 5, self.row['scenario']), [])

    def test_variants(self):
        report = self.load(self.file('json', [self.row, dict(self.row, variant=6)]))
        self.assertEqual(report['inserted'], 2)
        self.assertEqual(self.count(), 2)

    def test_duplicate_rows(self):
        report = self.load(self.file('csv', [self.row, self.row]))
        self.assertEqual((report['read'], report['inserted'], report['duplicates']), (2, 1, 1))

    def test_duplicate_json_key(self):
        path = self.root / 'bad.json'
        path.write_text('{"format":"plo-strategy-v1","records":[{"variant":5,"variant":6,"scenario":{},"actions":{}}]}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.load(path)

    def test_invalid_batch_no_writes(self):
        for bad in (dict(self.row, variant=5.0), dict(self.row, actions={'fold': .5}),
                    dict(self.row, scenario={}), dict(self.row, permission='allowed'),
                    dict(self.row, actions={'fold': float('nan')})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.load(self.file('json', [self.row, bad]))
            self.assertEqual(self.count(), 0)

    def test_tabular_header_and_row(self):
        for text in ('variant,scenario,action\n', 'variant,scenario,actions\n5,{},{} ,extra\n',
                     'variant,scenario,actions\n5.0,{},{}\n', 'variant,scenario,actions\n5,"unfinished'):
            path = self.root / 'bad.csv'
            path.write_text(text)
            with self.assertRaises(ValueError):
                self.load(path)

    def test_file_limits(self):
        path = self.file('json', [self.row, self.row])
        with patch.object(imp, 'MAX_BYTES', 1), self.assertRaises(ValueError):
            self.load(path)
        with patch.object(imp, 'MAX_ROWS', 1), self.assertRaises(ValueError):
            self.load(path)
        self.assertEqual(self.count(), 0)

    def test_empty_unknown_format_and_encoding(self):
        for path in (self.file('json', []), self.root / 'missing.csv', self.root / 'bad.zip'):
            with self.assertRaises(ValueError):
                self.load(path)
        path = self.root / 'bad.txt'
        path.write_bytes(b'\xff')
        with self.assertRaises(ValueError):
            self.load(path)

    def test_real_and_unknown_source_blocked(self):
        path = self.file('json', [self.row])
        for changes in (dict(synthetic=False), dict(synthetic=1), dict(source_id='missing')):
            with self.assertRaises(ValueError):
                self.load(path, **changes)
        self.assertEqual(self.count(), 0)

    def test_sql_failure_rolls_back(self):
        path = self.file('json', [self.row, dict(self.row, variant=6)])
        real = s.insert_prepared_record
        def fail_second(db, item):
            if item[0][1] == 6:
                raise sqlite3.IntegrityError('test failure')
            return real(db, item)
        with patch.object(s, 'insert_prepared_record', side_effect=fail_second), self.assertRaises(sqlite3.IntegrityError):
            self.load(path)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM scenarios').fetchone()[0], 0)

    def test_active_transaction_preserved(self):
        path = self.file('json', [self.row])
        self.db.execute('BEGIN')
        with self.assertRaises(ValueError):
            self.load(path)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()


if __name__ == '__main__':
    unittest.main()
