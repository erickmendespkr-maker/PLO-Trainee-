import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_reference_audit import EXPECTED, sha, validate_connection, audit


def fixture(db):
    db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    db.executemany('INSERT INTO metadata VALUES (?,?)',EXPECTED.items())
    db.execute('CREATE TABLE equity(rank INTEGER PRIMARY KEY,hand TEXT NOT NULL,suits TEXT NOT NULL,lo TEXT NOT NULL,hi TEXT NOT NULL,combos INTEGER NOT NULL)')
    db.execute('CREATE INDEX equity_descriptor ON equity(hand,suits)')


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close);fixture(self.db)
    def test_empty_rejected(self):
        with self.assertRaisesRegex(ValueError,'Incomplete reference'):validate_connection(self.db,orbit_audit=lambda d:None)
    def test_provenance(self):
        self.db.execute("UPDATE metadata SET value='GTO' WHERE key='kind'")
        with self.assertRaisesRegex(ValueError,'provenance'):validate_connection(self.db,orbit_audit=lambda d:None)
    def test_index(self):
        self.db.execute('DROP INDEX equity_descriptor');self.db.execute('CREATE INDEX equity_descriptor ON equity(rank)')
        with self.assertRaisesRegex(ValueError,'index'):validate_connection(self.db,orbit_audit=lambda d:None)
    def test_schema(self):
        self.db.execute('CREATE TABLE fake(x)')
        with self.assertRaisesRegex(ValueError,'schema'):validate_connection(self.db,orbit_audit=lambda d:None)
    def test_full_count_and_mismatch(self):
        # Synthetic structure: counts only, no actual equity or orbit certification.
        self.db.executemany('INSERT INTO equity VALUES (?,?,?,?,?,?)',((i,'A-A-T-9-9','ds','0.5','0.5',24 if i<=82121 else 12 if i<=134347 else 4) for i in range(1,134460)))
        # Adjust synthetic count to exact mass; never mark fixture as reviewed.
        current=self.db.execute('SELECT sum(combos) FROM equity').fetchone()[0]
        self.db.execute('UPDATE equity SET combos=combos+? WHERE rank=1',(2598960-current,))
        with self.assertRaisesRegex(ValueError,'orbit coverage'):validate_connection(self.db,orbit_audit=lambda d:{'status':'AGGREGATE_COUNTS_MISMATCH'})
    def test_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';p.write_bytes(b'abc');self.assertEqual(sha(p),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

if __name__=='__main__':unittest.main()
