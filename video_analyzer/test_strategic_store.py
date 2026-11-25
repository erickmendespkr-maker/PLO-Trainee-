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
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 3)
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


class PermissionTests(unittest.TestCase):
    setUp = StoreTests.setUp
    record = StoreTests.record
    def review(self, **changes):
        data = dict(status='allowed', local_use=True, redistribution=False,
                    reviewer='test reviewer', reviewed_on='2026-11-25',
                    evidence_ref='synthetic permission evidence', evidence_sha256='a'*64,
                    source_version='fixture v1', scope='synthetic local test only')
        data.update(changes)
        return s.record_permission_review(self.db, self.source, **data)

    def test_pending_and_approval(self):
        self.assertEqual(s.source_permission(self.db, self.source)['status'], 'pending')
        key = self.review()
        result = s.source_permission(self.db, self.source)
        self.assertEqual((result['id'], result['status'], result['local_use'], result['redistribution']),
                         (key, 'allowed', True, False))
        self.assertEqual(result['evidence_sha256'], 'a'*64)
        with self.assertRaises(ValueError):
            self.record(synthetic=False)

    def test_restriction_and_history(self):
        first = self.review()
        last = self.review(status='restricted', local_use=False)
        self.assertGreater(last, first)
        self.assertFalse(s.source_permission(self.db, self.source)['local_use'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_permission_reviews').fetchone()[0], 2)
        for sql in ('DELETE FROM source_permission_reviews',
                    "UPDATE source_permission_reviews SET status='pending'"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
            self.db.rollback()

    def test_invalid_review(self):
        for changes in ({'status':'unknown'}, {'reviewer':' '}, {'local_use':1},
                        {'status':'restricted'}, {'local_use':False},
                        {'status':'pending','local_use':False,'redistribution':True},
                        {'evidence_sha256':'bad'}, {'reviewed_on':'2026-02-30'},
                        {'reviewed_on':'20261125'}, {'scope':''}, {'source_version':''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review(**changes)
        self.assertEqual(s.source_permission(self.db, self.source)['status'], 'pending')

    def test_source_isolation(self):
        other = s.add_source(self.db, 'other fixture', 'test only', 'local')
        self.review()
        self.assertEqual(s.source_permission(self.db, other)['status'], 'pending')
        with self.assertRaises(KeyError):
            s.source_permission(self.db, 'missing')

    def test_review_persistence(self):
        self.review()
        self.db.close()
        db = s.connect(self.path)
        self.addCleanup(db.close)
        self.assertEqual(s.source_permission(db, self.source)['status'], 'allowed')

    def test_v2_migration(self):
        path = self.path.with_name('legacy.sqlite')
        db = sqlite3.connect(path)
        db.executescript(s.SCHEMA)
        source = s.add_source(db, 'legacy fixture', 'test only', 'local')
        record = s.add_record(db, source, 5, self.scenario, self.actions, synthetic=True)
        db.close()
        db = s.connect(path)
        self.addCleanup(db.close)
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
        self.assertEqual(db.execute('SELECT id FROM records').fetchone()[0], record)
        self.assertEqual(s.lookup(db, 5, self.scenario, synthetic=True), [(source, self.actions)])
        self.assertEqual(s.source_permission(db, source)['status'], 'pending')
        s.migrate_permissions(db)
        self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_failed_migration_rolls_back(self):
        path = self.path.with_name('broken.sqlite')
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        db.executescript(s.SCHEMA)
        db.execute('CREATE TABLE source_review_latest(x INTEGER)')
        db.commit()
        with self.assertRaises(sqlite3.OperationalError):
            s.connect(path)
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='source_permission_reviews'").fetchone())


if __name__ == '__main__':
    unittest.main()
