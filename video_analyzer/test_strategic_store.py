import sqlite3
import tempfile
import unittest
from pathlib import Path

import strategic_store as s


class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'store.sqlite'
        self.db = s.connect(self.path)
        self.addCleanup(self.db.close)
        self.source = s.add_source(self.db, 'fixture', 'test only', 'local')
        self.scenario = {'position': 'BTN', 'stack_bb': 100}
        self.actions = {'fold': .25, 'raise': .75}

    def record(self, variant=5, scenario=None, actions=None, synthetic=True):
        return s.add_record(self.db, self.source, variant,
                            self.scenario if scenario is None else scenario,
                            self.actions if actions is None else actions, synthetic=synthetic)

    def test_schema(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 2)
        names = {r[0] for r in self.db.execute('SELECT name FROM sqlite_master')}
        self.assertTrue({'sources', 'scenarios', 'records', 'records_lookup'} <= names)
        self.assertEqual(self.db.execute('PRAGMA foreign_keys').fetchone()[0], 1)

    def test_persistence(self):
        self.record()
        self.db.close()
        db = s.connect(self.path)
        self.addCleanup(db.close)
        self.assertEqual(s.lookup(db, 5, self.scenario, synthetic=True), [(self.source, self.actions)])

    def test_source_provenance(self):
        with self.assertRaises(ValueError):
            s.add_source(self.db, 'fixture', '', 'local')
        self.assertEqual(self.db.execute('SELECT permission FROM sources').fetchone()[0], 'pending')
        self.assertEqual(self.source, s.add_source(self.db, 'fixture', 'test only', 'local'))

    def test_dedup(self):
        self.assertEqual(self.record(), self.record(scenario={'stack_bb': 100, 'position': 'BTN'}))
        self.assertEqual(self.db.execute('SELECT count(*) FROM records').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM scenarios').fetchone()[0], 1)

    def test_variant_separation(self):
        self.record()
        self.assertEqual(s.lookup(self.db, 6, self.scenario, synthetic=True), [])
        self.record(6)
        self.assertEqual(len(s.lookup(self.db, 6, self.scenario, synthetic=True)), 1)

    def test_real_data_disabled(self):
        self.record()
        self.assertEqual(s.lookup(self.db, 5, self.scenario), [])
        with self.assertRaises(ValueError):
            self.record(synthetic=False)
        with self.assertRaises(ValueError):
            self.record(synthetic=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE records SET synthetic=0')
        self.db.rollback()

    def test_invalid_variant(self):
        for variant in (4, 5.0, True, '5', None):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                self.record(variant)
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                s.lookup(self.db, variant, self.scenario)

    def test_invalid_actions(self):
        for actions in ({}, {'call': .5}, {'call': True}, {'call': float('nan')},
                        {'call': float('inf')}, {'fold': -1, 'call': 2}, {'dance': 1}):
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                self.record(actions=actions)

    def test_invalid_scenario(self):
        for scenario in ({}, [], {1: 'value'}, {'stack_bb': float('nan')}):
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                self.record(scenario=scenario)

    def test_atomic_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            s.add_record(self.db, 'missing', 5, self.scenario, self.actions, synthetic=True)
        self.assertEqual(self.db.execute('SELECT count(*) FROM scenarios').fetchone()[0], 0)

    def test_integrity(self):
        self.record()
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_legacy_and_unknown_versions(self):
        for version in (1, 99):
            self.db.execute('PRAGMA user_version=' + str(version))
            self.db.commit()
            with self.assertRaises(ValueError):
                s.connect(self.path)
            self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], version)

    def test_unversioned_nonempty(self):
        other = self.path.with_name('other.sqlite')
        db = sqlite3.connect(other)
        db.execute('CREATE TABLE unrelated(id INTEGER)')
        db.close()
        with self.assertRaises(ValueError):
            s.connect(other)

    def test_index_plan(self):
        plan = self.db.execute('EXPLAIN QUERY PLAN SELECT source_id,payload FROM records WHERE scenario_id=? AND synthetic=?', ('x', 1)).fetchall()
        self.assertTrue(any('records_lookup' in row[-1] for row in plan), plan)


if __name__ == '__main__':
    unittest.main()
