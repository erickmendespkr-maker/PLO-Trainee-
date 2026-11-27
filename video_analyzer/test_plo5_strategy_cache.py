import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from test_plo5_post_gto_multiway import fixture
from plo5_post_gto_multiway import prior
from plo5_strategy_cache import solve_cached,specification,lookup,pack,unpack


class StrategyCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'cache.sqlite';self.c=fixture(3,2)
    def test_lossless_reopen(self):
        a=solve_cached(self.path,self.c,10,rake_on_fold=False,include_deal_values=True)
        b=solve_cached(self.path,self.c,10,rake_on_fold=False,include_deal_values=True)
        self.assertFalse(a['cache_hit']);self.assertTrue(b['cache_hit']);self.assertEqual(a['result'],b['result'])
        self.assertLess(a['stored_bytes'],a['raw_bytes'])
        self.assertEqual(lookup(b,[],self.c['ranges']['SB'][0]['cards'])['status'],'CONDITIONAL_POLICY')
        self.assertEqual(lookup(b,[['SB','bet',999]],self.c['ranges']['SB'][0]['cards'])['status'],'UNMODELED_HISTORY')
    def test_identity_isolation(self):
        c=self.c;key=lambda **kw:specification(c,**dict({'rake_on_fold':False},**kw))[0]
        base=key();self.assertNotEqual(base,key(rake_on_fold=True));self.assertNotEqual(base,key(iterations=101))
        self.assertNotEqual(base,key(include_deal_values=True));self.assertNotEqual(base,key(pot_bps=(5000,)))
        self.assertEqual(key(pot_bps=(5000,10000)),key(pot_bps=(10000,5000,5000)))
        joint=[dict(holdings=[list(k) for k in h],weight=w) for h,w in prior(c)[:1]]
        self.assertNotEqual(base,key(joint=joint));self.assertNotEqual(base,key(max_work=100))
        self.assertNotEqual(base,specification(dict(c,rake_bps=500),rake_on_fold=False)[0])
    def test_corruption_and_bomb(self):
        a=solve_cached(self.path,self.c,1,rake_on_fold=False)
        with closing(sqlite3.connect(self.path)) as con,con:con.execute('UPDATE strategy_zlib_v1 SET checksum=?',('0'*64,))
        with self.assertRaisesRegex(ValueError,'checksum'):solve_cached(self.path,self.c,1,rake_on_fold=False)
        b,n,h=pack({'a':'x'*10000})
        for blob,size in ((b,1),(b+b, n),(b[:-1],n)):
            with self.assertRaises(ValueError):unpack(blob,size,h)
    def test_native_cache(self):
        exe=os.environ.get('PLO5_MULTIWAY_EXE')
        if not exe:self.skipTest('native executable absent')
        a=solve_cached(self.path,self.c,10,rake_on_fold=False,cfr_executable=exe)
        b=solve_cached(self.path,self.c,10,rake_on_fold=False,cfr_executable=exe)
        c=solve_cached(self.path,self.c,10,rake_on_fold=False)
        self.assertTrue(b['cache_hit']);self.assertNotEqual(a['cache_key'],c['cache_key'])
        for x,y in zip(a['result']['values_bb'],c['result']['values_bb']):self.assertAlmostEqual(x,y,places=8)

if __name__=='__main__':unittest.main()
