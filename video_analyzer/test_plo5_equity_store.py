import sqlite3
import tempfile
import unittest
from pathlib import Path
import plo5_equity_store as e


class EquityTests(unittest.TestCase):
    def test_valid_row(self):
        self.assertEqual(list(e.parse_rows(','.join(e.FIELDS)+'\n1,A-A-T-9-9,ds,0.65,0.66,12\n')),
                         [(1,'A-A-T-9-9','ds','0.65','0.66',12)])

    def test_bad_rows(self):
        for row in ('2,A-A-T-9-9,ds,0.65,0.66,12', '1,A-A-A-A-A,ds,0.65,0.66,12',
                    '1,A-A-T-9-9,xx,0.65,0.66,12', '1,A-A-T-9-9,ds,NaN,0.66,12',
                    '1,A-A-T-9-9,ds,0.67,0.66,12', '1,A-A-T-9-9,ds,0.65,0.66,13',
                    '1,A-A-T-9-9,ds,0.65,0.66,12,extra'):
            with self.subTest(row=row), self.assertRaises(ValueError):
                list(e.parse_rows(','.join(e.FIELDS)+'\n'+row+'\n'))

    def test_bad_schema(self):
        with self.assertRaises(ValueError):
            list(e.parse_rows('rank,hand\n1,A-A-T-9-9\n'))

    def test_unreviewed_file_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/'input.csv', Path(tmp)/'out.db'
            src.write_text('unreviewed')
            with self.assertRaises(ValueError):
                e.import_csv(src,dst)
            self.assertFalse(dst.exists())

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)/'out.db'
            dst.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                e.import_csv(Path(tmp)/'input.csv',dst)
            self.assertEqual(dst.read_bytes(),b'keep')

    def test_descriptor_lookup(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('CREATE TABLE equity(rank,hand,suits,lo,hi,combos)')
        db.executemany('INSERT INTO equity VALUES (?,?,?,?,?,?)', [(1,'A-A-T-9-9','ds','0.60','0.61',12),
                        (2,'A-A-T-9-9','ds','0.50','0.52',12),(3,'A-A-T-9-9','ss','0.40','0.42',24)])
        result = e.lookup_descriptor(db,'A-A-T-9-9','ds')
        self.assertEqual((result['status'],result['matches'],result['equity_lo'],result['equity_hi']),
                         ('AMBIGUOUS_DESCRIPTOR',2,'0.50','0.61'))
        self.assertFalse(result['gto'])
        self.assertFalse(result['exact_suit_match'])
        self.assertEqual(e.lookup_descriptor(db,'A-A-T-9-9','ss')['status'],'DESCRIPTOR_ONLY')
        self.assertEqual(e.lookup_descriptor(db,'A-A-T-9-9','mono')['status'],'NO_MATCH')
