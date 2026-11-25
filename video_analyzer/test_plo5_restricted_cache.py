import unittest
from plo5_restricted_cache import connect, resolve
from test_plo5_cfr_restricted import PAIRS

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:');self.addCleanup(self.db.close)
    def test_reuse(self):
        a=resolve(self.db,PAIRS,2,1);b=resolve(self.db,PAIRS,2,1)
        self.assertFalse(a.pop('cache_hit'));self.assertTrue(b.pop('cache_hit'));self.assertEqual(a,b)
    def test_distinct_options(self):
        resolve(self.db,PAIRS,2,1)
        self.assertFalse(resolve(self.db,PAIRS,2,1,target=.02)['cache_hit'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM restricted_solutions').fetchone()[0],2)
    def test_not_converged(self):
        for _ in range(2):self.assertFalse(resolve(self.db,PAIRS,2,1,iterations=1,target=0)['cache_hit'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM restricted_solutions').fetchone()[0],0)
    def test_tamper(self):
        resolve(self.db,PAIRS,2,1)
        self.db.execute("UPDATE restricted_solutions SET policy='{}'")
        with self.assertRaises(ValueError):resolve(self.db,PAIRS,2,1)
    def test_incorrect_policy(self):
        resolve(self.db,PAIRS,2,1)
        self.db.execute('UPDATE restricted_solutions SET policy=?',('{"hero_bet_probabilities":[1,1],"opponent_call_probabilities":[0],"iterations":1}',))
        with self.assertRaisesRegex(ValueError,'requested gap'):resolve(self.db,PAIRS,2,1)

if __name__=='__main__':unittest.main()
