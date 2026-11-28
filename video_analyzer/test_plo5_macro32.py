import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from plo5_strategy_cache import connection, prune, solve_cached
from test_plo5_post_gto_multiway import fixture
from plo5_continuation_bounds import envelopes
from test_plo5_post_gto_river import context,NUT,CATCH,BOARD
import plo5_post_gto_tree as post

class PerformanceTests(unittest.TestCase):
    def test_cache_quota_fifo_and_reuse(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'cache.sqlite';con=connection(p)
            with con:
                for i in range(5):con.execute('INSERT INTO strategy_zlib_v1 VALUES (?,?,?,?,?)',(str(i),b'spec',100,'a'*64,b'x'*100))
                stats=prune(con,max_bytes=1000,max_entries=2)
            self.assertEqual(stats['entries'],2);self.assertEqual(stats['removed'],3)
            self.assertEqual([x[0] for x in con.execute('SELECT cache_key FROM strategy_zlib_v1 ORDER BY rowid')],['3','4'])
            with con:self.assertEqual(prune(con,max_bytes=0)['entries'],0)
            con.close()
            a=solve_cached(p,fixture(3,2),1,rake_on_fold=False);b=solve_cached(p,fixture(3,2),1,rake_on_fold=False)
            self.assertTrue(b['cache_hit']);self.assertEqual(a['result'],b['result'])
    def test_quota_rollback_and_validation(self):
        with tempfile.TemporaryDirectory() as t:
            con=connection(Path(t)/'cache.sqlite')
            with con:con.execute('INSERT INTO strategy_zlib_v1 VALUES (?,?,?,?,?)',('x',b'spec',100,'a'*64,b'x'*100))
            with self.assertRaises(ValueError):
                with con:prune(con,max_entries=0);prune(con,max_bytes=-1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM strategy_zlib_v1').fetchone()[0],1);con.close()
    @unittest.skipUnless(os.environ.get('PLO5_RANK_WORKER_EXE'),'Native worker required')
    def test_batched_native_terminal_budget_exact(self):
        from plo5_rank_worker import RankWorker
        s=post.step(post.start(context([(NUT,1)],[(CATCH,1)],board=BOARD[:4])),'BB','bet',2)
        deal=[((tuple(sorted(NUT)),tuple(sorted(CATCH))),Fraction(1))]
        class Count:
            def __init__(self,w):self.w=w;self.calls=0
            def lookup(self,*a):self.calls+=1;return self.w.lookup(*a)
        with RankWorker(os.environ['PLO5_RANK_WORKER_EXE']) as w:
            for n in (1,4,100):
                a=dict(rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=n)
                c=Count(w);ref=envelopes(s,'BTN',deal,[('call',2)],**a);r=envelopes(s,'BTN',deal,[('call',2)],rank_worker=c,**a)
                self.assertEqual(r,ref);self.assertLessEqual(c.calls,1)

if __name__=='__main__':unittest.main()
