import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
from plo5_singleflight import SingleFlight


class SingleFlightTests(unittest.TestCase):
    def test_parallel_same_key(self):
        cache=SingleFlight(3); entered=Event(); release=Event(); calls=[]
        def read():
            calls.append(1); entered.set()
            if not release.wait(3): raise RuntimeError('timeout')
            return {'candidate':[1]}
        with ThreadPoolExecutor(3) as pool:
            leader=pool.submit(cache.get,('pot',b'1'),read)
            self.assertTrue(entered.wait(2))
            others=[pool.submit(cache.get,('pot',b'1'),read) for _ in range(2)]
            try:
                end=time.monotonic()+2
                while cache.stats()['shared_inflight']<2 and time.monotonic()<end: time.sleep(.001)
                self.assertEqual(cache.stats()['shared_inflight'],2)
            finally: release.set()
            values=[f.result(timeout=3) for f in [leader]+others]
        self.assertEqual(len(calls),1);values[0]['candidate'].append(2)
        self.assertEqual(values[1],{'candidate':[1]})
        self.assertEqual(cache.get(('pot',b'1'),read),{'candidate':[1]})
        self.assertEqual(cache.stats()['hits'],1)
    def test_independent_keys(self):
        cache=SingleFlight(2);a=Event();b=Event()
        def first():
            a.set();return b.wait(2)
        def second():
            b.set();return a.wait(2)
        with ThreadPoolExecutor(2) as pool:
            f=pool.submit(cache.get,('a',b'1'),first);g=pool.submit(cache.get,('b',b'1'),second)
            self.assertTrue(f.result(timeout=3));self.assertTrue(g.result(timeout=3))
    def test_failure_retry(self):
        cache=SingleFlight();entered=Event();release=Event()
        def fail():
            entered.set();release.wait(3);raise ValueError('OCR failed')
        with ThreadPoolExecutor(2) as pool:
            f=pool.submit(cache.get,('pot',b'1'),fail);self.assertTrue(entered.wait(2));g=pool.submit(cache.get,('pot',b'1'),fail)
            try:
                end=time.monotonic()+2
                while cache.stats()['shared_inflight']<1 and time.monotonic()<end:time.sleep(.001)
                self.assertEqual(cache.stats()['shared_inflight'],1)
            finally:release.set()
            for future in (f,g):
                with self.assertRaisesRegex(ValueError,'OCR failed'):future.result(timeout=3)
        self.assertEqual(cache.stats()['entries'],0);self.assertEqual(cache.get(('pot',b'1'),lambda:5),5)
    def test_lru(self):
        c=SingleFlight(2)
        for k in (b'a',b'b',b'a',b'c',b'b'):c.get(('x',k),lambda:1)
        self.assertEqual(c.stats()['misses'],4);self.assertEqual(c.stats()['entries'],2)
    def test_disabled(self):
        c=SingleFlight(0)
        for i in range(3):self.assertEqual(c.get(('a',b'a'),lambda:i),i)
        self.assertEqual(c.stats()['misses'],3);self.assertEqual(c.stats()['entries'],0)
    def test_bad_capacity(self):
        for x in (-1,2049,True,1.5):
            with self.assertRaises(ValueError):SingleFlight(x)

if __name__=='__main__':unittest.main()
