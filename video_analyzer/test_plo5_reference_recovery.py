import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_reference_audit import recover

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dest=Path(self.tmp.name)/'new.sqlite';self.csv=Path(self.tmp.name)/'source.csv'
        self.csv.write_text('not the licensed snapshot')
    def test_real_import_rejects_unreviewed_csv(self):
        with self.assertRaisesRegex(ValueError,'reviewed licensed snapshot'):recover(self.dest,self.csv)
        self.assertFalse(self.dest.exists())
    def test_reject_existing(self):
        self.dest.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'New database'):recover(self.dest,self.csv)
        self.assertEqual(self.dest.read_bytes(),b'original')
    def test_audit_failure_no_publication(self):
        def create(source,dest):dest.write_bytes(b'candidate')
        with patch('plo5_equity_store.import_csv',side_effect=create),patch('plo5_reference_audit.audit',side_effect=ValueError('audit failed')):
            with self.assertRaisesRegex(ValueError,'audit failed'):recover(self.dest,self.csv)
        self.assertFalse(self.dest.exists());self.assertEqual(list(Path(self.tmp.name).glob('.plo5-reference-*')),[])
    def test_publication_after_audit(self):
        def create(source,dest):dest.write_bytes(b'candidate')
        def audit(path,*,csv_path):
            self.assertFalse(self.dest.exists());self.assertEqual(path.read_bytes(),b'candidate');return {'test_fixture':True}
        with patch('plo5_equity_store.import_csv',side_effect=create),patch('plo5_reference_audit.audit',side_effect=audit):
            self.assertEqual(recover(self.dest,self.csv),{'test_fixture':True})
        self.assertEqual(self.dest.read_bytes(),b'candidate')
    def test_destination_race(self):
        def create(source,dest):dest.write_bytes(b'candidate')
        def audit(path,*,csv_path):self.dest.write_bytes(b'other');return {}
        with patch('plo5_equity_store.import_csv',side_effect=create),patch('plo5_reference_audit.audit',side_effect=audit):
            with self.assertRaises(FileExistsError):recover(self.dest,self.csv)
        self.assertEqual(self.dest.read_bytes(),b'other')

if __name__=='__main__':unittest.main()
