import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from plo5_river_cache_open import open_cache

class OpenTests(unittest.TestCase):
    def test_new_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'cache.db'
            with closing(open_cache(p)) as db:self.assertEqual(db.execute('SELECT count(*) FROM restricted_solutions').fetchone(),(0,))
            with closing(open_cache(p)) as db:self.assertEqual(db.execute('SELECT count(*) FROM restricted_solutions').fetchone(),(0,))
    def test_unrelated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'other.db'
            with closing(sqlite3.connect(p)) as db:db.execute('CREATE TABLE hands(x)');db.commit()
            with self.assertRaisesRegex(ValueError,'dedicated'):open_cache(p)
            with closing(sqlite3.connect(p)) as db:self.assertEqual(db.execute('SELECT name FROM sqlite_master').fetchall(),[('hands',)])
    def test_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.db'
            with self.assertRaisesRegex(ValueError,'Unsafe'):open_cache(p,protected=[p])
            self.assertFalse(p.exists())
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'link';p.symlink_to(Path(tmp)/'target')
            with self.assertRaisesRegex(ValueError,'Unsafe'):open_cache(p)

if __name__=='__main__':unittest.main()
